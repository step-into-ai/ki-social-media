import importlib.util, json, pathlib, subprocess, tempfile, threading, unittest, urllib.request, urllib.error
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('collector',pathlib.Path(__file__).parents[1]/'collector'/'service.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();s.DATA=pathlib.Path(self.tmp.name);s.initialize()
        with s.db() as c:
            c.execute('DELETE FROM sources')
            self.ident=c.execute("INSERT INTO sources(platform,handle,title,mode) VALUES('youtube','creator','Creator','both')").lastrowid
        self.source={'id':self.ident,'platform':'youtube','handle':'creator','title':'Creator','channel_id':None,'mode':'both','failures':0}
    def tearDown(self):self.tmp.cleanup()
    def video(self,ident,kind):return {'external_id':ident,'format':kind,'title':ident,'url':'https://www.youtube.com/watch?v='+ident,'published_at':'2026-11-15T12:00:00Z'}
    def test_dedup_preserves_seen_and_format_separation(self):
        s.save_success(self.source,[self.video('abcdefghijk','long'),self.video('123456789ab','short')],{},[])
        with s.db() as c:c.execute('UPDATE videos SET seen=1 WHERE external_id=?',('abcdefghijk',))
        s.save_success(self.source,[self.video('abcdefghijk','long')],{},[])
        self.assertEqual(len(s.feed('long',unseen=False)),1);self.assertEqual(len(s.feed('short')),1)
        self.assertEqual(s.feed('long',unseen=False)[0]['seen'],1)
        self.assertEqual(s.feed('long',unseen=True),[])
        with s.db() as c:c.execute("UPDATE sources SET mode='long' WHERE id=?",(self.ident,))
        self.assertEqual(s.feed('short'),[])
        with s.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],2)
    def test_failure_preserves_videos_and_success_time(self):
        s.save_success(self.source,[self.video('abcdefghijk','long')],{},[])
        before=s.sources()[0]['success_at']
        with patch.object(s,'collect',side_effect=ValueError('Temporary failure')):self.assertFalse(s.refresh_one(self.source))
        source=s.sources()[0]
        self.assertEqual(source['status'],'error');self.assertEqual(source['success_at'],before)
        self.assertEqual(len(s.feed('long')),1)
    def test_creator_url_validation(self):
        self.assertEqual(s.normalize_source('https://www.youtube.com/@Julian-Ivanov','both')['mode'],'both')
        self.assertEqual(s.normalize_source('https://www.tiktok.com/@lucaoncamera','both')['mode'],'short')
        for url in ['http://127.0.0.1/','https://www.youtube.com.evil.example/@creator','https://www.youtube.com:443/@creator','https://www.youtube.com/@creator/../../api','https://user:pass@www.youtube.com/@creator']:
            with self.assertRaises(ValueError):s.normalize_source(url,'both')

    def test_initial_five_then_unseen_backlog_is_not_truncated_or_resurrected(self):
        initial=[{**self.video(f'v{i:010d}','long'),'published_at':f'2026-11-16T12:{i:02d}:00Z'} for i in range(10)]
        s.save_success(self.source,initial,{},[])
        self.assertEqual({v['external_id'] for v in s.feed('long')},{f'v{i:010d}' for i in range(5,10)})
        additions=[{**self.video(f'v{i:010d}','long'),'published_at':f'2026-11-16T12:{i:02d}:00Z'} for i in range(10,20)]
        s.save_success(self.source,initial+additions,{},[])
        self.assertEqual(len(s.feed('long')),15)
        s.save_success(self.source,initial+additions,{},[])
        self.assertEqual(len(s.feed('long')),15)
        with s.db() as c:c.execute('UPDATE videos SET seen=1 WHERE feed_eligible=1')
        s.initialize()
        self.assertEqual(s.feed('long'),[])
        with s.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM videos').fetchone()[0],20)

    def test_creator_mix_and_independent_short_long_start(self):
        s.save_success(self.source,[self.video(f'a{i:010d}','long') for i in range(8)]+[self.video(f's{i:010d}','short') for i in range(8)],{},[])
        with s.db() as c:second=c.execute("INSERT INTO sources(platform,handle,title,mode) VALUES('youtube','second','Second','both')").lastrowid
        s.save_success({**self.source,'id':second},[self.video(f'b{i:010d}','long') for i in range(8)],{},[])
        self.assertEqual(len(s.feed('short')),5)
        sequence=[v['source_id'] for v in s.feed('long')[:4]]
        self.assertEqual(set(sequence),{self.ident,second});self.assertNotEqual(sequence[0],sequence[1])
        self.assertEqual(sequence[:2],sequence[2:])

    def test_link_only_posts_are_hidden_and_changed_text_invalidates_translation(self):
        for text in ['https://t.co/abc','Source 1','Quelle:','Source 2 https://t.co/abc']:
            self.assertFalse(s.has_story_text(text))
        self.assertTrue(s.has_story_text('Eine neue Analyse: https://example.com'))
        source=self.x_source();rows=s.parse_x_items(self.x_items(),'kimmonismus')
        s.save_success(source,rows,{},[])
        job=s.claim_translations()[0]
        self.assertEqual(s.complete_translations([{'id':job['id'],'text_hash':job['text_hash'],'text_de':'Ein echter übersetzter Beitrag.'}]),1)
        s.save_success(source,rows,{},[])
        self.assertEqual(s.posts()[0]['text_de'],'Ein echter übersetzter Beitrag.')
        rows[0]['text']='Updated source text'
        s.save_success(source,rows,{},[])
        self.assertEqual(s.posts()[0]['text_de'],'')
        self.assertEqual(s.complete_translations([{'id':job['id'],'text_hash':job['text_hash'],'text_de':'Veraltete Fassung'}]),0)
        rows[0]['text']='https://t.co/abc';s.save_success(source,rows,{},[])
        self.assertEqual(s.posts(),[])
        self.assertEqual(s.normalize_source('https://x.com/Kimmonismus','both'),{'platform':'x','handle':'kimmonismus','channel_id':None,'mode':'posts'})
        self.assertEqual(s.normalize_source('https://twitter.com/kimmonismus','short')['mode'],'posts')
        for url in ['https://x.com/home','https://x.com/kimmonismus/status/123','https://x.com/kimmonismus?token=x','https://x.com.evil.test/creator']:
            with self.assertRaises(ValueError):s.normalize_source(url,'both')

    def x_source(self,handle='kimmonismus'):
        with s.db() as c:
            ident=c.execute("INSERT INTO sources(platform,handle,title,mode) VALUES('x',?,?,'posts')",(handle,handle)).lastrowid
        return {'id':ident,'platform':'x','handle':handle,'title':handle,'mode':'posts','failures':0}

    def x_items(self):
        return [{'url':'https://x.com/kimmonismus/status/2122163929736794622','text':'A real example of post text',
                 'raw':{'images':['https://pbs.twimg.com/media/sample.jpg','https://evil.example/track.jpg'],
                        'auth_token':'should-never-be-saved'}}]

    def test_x_pinned_posts_have_actual_date_and_media_is_allowlisted(self):
        posts=s.parse_x_items(self.x_items(),'kimmonismus')
        self.assertEqual(posts[0]['published_at'][:10],'2026-11-16')
        self.assertEqual(posts[0]['media'],['https://pbs.twimg.com/media/sample.jpg'])
        self.assertNotIn('should-never-be-saved',json.dumps(posts))
        with self.assertRaises(ValueError):s.parse_x_items([{'text':'Missing ID'}],'kimmonismus')

    def test_x_duplicates_seen_deactivation_and_removal(self):
        source=self.x_source();posts=s.parse_x_items(self.x_items(),'kimmonismus')
        s.save_success(source,posts,{},[])
        with s.db() as c:c.execute('UPDATE posts SET seen=1,favorite=1')
        s.save_success(source,posts,{},[])
        self.assertEqual(len(s.posts()),1);self.assertEqual(s.posts()[0]['seen'],1);self.assertEqual(s.posts()[0]['favorite'],1)
        self.assertEqual(s.feed('short'),[]);self.assertEqual(s.feed('long'),[])
        self.assertEqual(s.sources()[-1]['post_count'],1)
        self.assertEqual(s.posts(unseen=True),[])
        with s.db() as c:c.execute('UPDATE sources SET enabled=0 WHERE id=?',(source['id'],))
        self.assertEqual(s.posts(),[])
        with s.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM posts').fetchone()[0],1)
            c.execute('DELETE FROM sources WHERE id=?',(source['id'],))
            self.assertEqual(c.execute('SELECT count(*) FROM posts').fetchone()[0],0)

    def test_x_same_repost_in_two_subscriptions_does_not_lose_creator_filter(self):
        a=self.x_source();b=self.x_source('othercreator')
        posts=s.parse_x_items(self.x_items(),'kimmonismus')
        s.save_success(a,posts,{},[]);s.save_success(b,posts,{},[])
        self.assertEqual(len(s.posts(a['id'])),1);self.assertEqual(len(s.posts(b['id'])),1)
        self.assertNotEqual(s.posts(a['id'])[0]['id'],s.posts(b['id'])[0]['id'])

    def test_x_upstream_login_error_is_sanitized_and_preserves_posts(self):
        source=self.x_source();s.save_success(source,s.parse_x_items(self.x_items(),'kimmonismus'),{},[])
        response=subprocess.CompletedProcess([],1,json.dumps({'ok':False,'error':{'code':'NEED_LOGIN','message':'auth_token=SECRET'}}),'ct0=SECRET')
        with patch.object(s.pathlib.Path,'is_file',return_value=True),patch.object(s.subprocess,'run',return_value=response):
            self.assertFalse(s.refresh_one(source))
        self.assertEqual(len(s.posts()),1)
        self.assertIn('X-Anmeldung',s.sources()[-1]['message'])
        self.assertNotIn('SECRET',json.dumps(s.sources()))
    def test_youtube_uses_selected_tab_and_explicit_shorts(self):
        card={'lockupViewModel':{'contentType':'LOCKUP_CONTENT_TYPE_VIDEO','contentId':'abcdefghijk','metadata':{'lockupMetadataViewModel':{'title':{'content':'Long'}}}}}
        short={'shortsLockupViewModel':{'onTap':{'innertubeCommand':{'reelWatchEndpoint':{'videoId':'123456789ab'}}},'overlayMetadata':{'primaryText':{'content':'Short'}}}}
        state={'contents':{'twoColumnBrowseResultsRenderer':{'tabs':[{'tabRenderer':{'selected':True,'content':{'cards':[card,short]}}}]}}}
        body='var ytInitialData = '+json.dumps(state)+';'
        longs,_=s.parse_youtube_tab(body,'long');shorts,_=s.parse_youtube_tab(body,'short')
        self.assertEqual([v['external_id'] for v in longs],['abcdefghijk'])
        self.assertEqual([v['external_id'] for v in shorts],['123456789ab'])
    def test_tiktok_rejects_challenge_and_wrong_author(self):
        with self.assertRaises(ValueError):s.parse_tiktok('<html>challenge</html>','creator')
        state={'source':{'data':{'/embed/@creator':{'userInfo':{'code':200},'videoList':[{'id':'7708159446706343199','authorUniqueId':'different'}]}}}}
        videos,_=s.parse_tiktok('<script id="__FRONTITY_CONNECT_STATE__">'+json.dumps(state)+'</script>','creator')
        self.assertEqual(videos,[])
    def test_api_requires_auth_and_pairing_code_is_single_use(self):
        s.TOKEN='t'*40;s.PAIR='code-123';s.PAIR_EXPIRES=9999999999;s.PAIR_ATTEMPTS.clear()
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/api/sources')
            self.assertEqual(error.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/api/posts')
            self.assertEqual(error.exception.code,401)
            request=lambda:urllib.request.Request(base+'/api/pair',data=json.dumps({'code':s.PAIR}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request()) as r:self.assertEqual(json.load(r)['token'],s.TOKEN)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request())
            self.assertEqual(error.exception.code,403)
            with urllib.request.urlopen(urllib.request.Request(base+'/api/sources',headers={'Authorization':'Bearer '+s.TOKEN})) as r:self.assertEqual(len(json.load(r)['sources']),1)
            auth={'Authorization':'Bearer '+s.TOKEN,'Content-Type':'application/json'}
            with patch.object(s,'refresh',return_value=True):
                req=urllib.request.Request(base+'/api/source',data=json.dumps({'url':'https://x.com/Kimmonismus'}).encode(),headers=auth)
                with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
                source=s.sources()[-1]
                self.assertEqual(source['mode'],'posts')
                req=urllib.request.Request(base+'/api/source',data=json.dumps({'id':source['id'],'mode':'posts','enabled':True}).encode(),headers=auth)
                with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
            s.save_success(source,s.parse_x_items(self.x_items(),'kimmonismus'),{},[])
            with urllib.request.urlopen(urllib.request.Request(base+'/api/posts',headers=auth)) as r:
                post=json.load(r)['posts'][0]
                self.assertEqual(post['handle'],'kimmonismus');self.assertNotIn('raw',post)
            req=urllib.request.Request(base+'/api/post',data=json.dumps({'id':post['id'],'seen':True,'favorite':True}).encode(),headers=auth)
            with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
            self.assertEqual(s.posts()[0]['favorite'],1)
            req=urllib.request.Request(base+'/api/seen',data=json.dumps({'ids':['youtube:absent-id']}).encode(),headers=auth)
            with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
            req=urllib.request.Request(base+'/internal/translation/claim',data=b'{}',headers=auth)
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,401)
            s.TRANSLATOR_TOKEN='r'*40
            translator={'Authorization':'Bearer '+s.TRANSLATOR_TOKEN,'Content-Type':'application/json'}
            req=urllib.request.Request(base+'/internal/translation/claim',data=b'{"limit":1}',headers=translator)
            with urllib.request.urlopen(req) as r:job=json.load(r)['jobs'][0]
            req=urllib.request.Request(base+'/internal/translation/result',data=json.dumps({'results':[{'id':job['id'],'text_hash':job['text_hash'],'text_de':'Ein deutscher Beitrag.'}]}).encode(),headers=translator)
            with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['saved'],1)
            self.assertEqual(s.posts()[0]['text_de'],'Ein deutscher Beitrag.')
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
