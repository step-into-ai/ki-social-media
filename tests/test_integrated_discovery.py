import hashlib,json,pathlib,tempfile,time,unittest,threading,urllib.request
from unittest.mock import patch
from test_newsroom import s,n

class IntegratedDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();s.DATA=pathlib.Path(self.tmp.name);s.initialize();s.newsroom.set_settings({'enabled':True})
        with s.db() as c:c.execute('DELETE FROM sources')
    def tearDown(self):self.tmp.cleanup()
    def suggestion(self,platform='x',ident='suggestion'):
        external=str((int(time.time()*1000)-1288834974657)<<22) if platform=='x' else 'abcdefghijk'
        url='https://x.com/newcreator/status/'+external if platform=='x' else 'https://www.youtube.com/watch?v='+external
        with s.db() as c:
            run=c.execute("INSERT INTO discovery_runs(slot,started_at) VALUES(?,?)",(ident,s.utc())).lastrowid
            c.execute('''INSERT INTO suggestions(id,run_id,platform,handle,creator,profile_url,url,title,evidence,reason,published_at,topic,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(ident,run,platform,'newcreator','New Creator','https://www.youtube.com/@newcreator' if platform=='youtube' else 'https://x.com/newcreator',
              url,'Ein praktisches KI-Tutorial','Nur ein kurzer Suchauszug.','Ein passender neuer Creator.',s.utc(),'KI',s.utc()))
        return n.suggestions()[0],external
    def hydrate_video(self,language='de',fmt='long'):
        item,external=self.suggestion('youtube')
        data={'external_id':external,'kind':'video','format':fmt,'title':item['title'],'url':item['url'],
          'thumbnail':'https://i.ytimg.com/vi/'+external+'/hqdefault.jpg','text':'','media':[],
          'language':language,'language_basis':'Verifizierte Audiosprache'}
        with patch.object(n,'hydrate_one',return_value=data):n.hydrate_suggestions()
        return item,external
    def test_full_x_post_is_integrated_and_translated_without_subscribing(self):
        item,external=self.suggestion();text='Der vollständige Originalbeitrag mit konkreten Details. '*90
        with patch.object(n,'reach',return_value=[{'url':'https://x.com/i/status/'+external,'text':text}]):n.hydrate_suggestions()
        rows=s.news();self.assertEqual(len(rows),1);post=rows[0]
        self.assertTrue(post['is_discovery']);self.assertEqual(post['kind'],'x');self.assertEqual(post['text'],text.strip())
        self.assertGreater(len(post['text']),2000);self.assertEqual(post['author'],'newcreator');self.assertEqual(s.sources(),[])
        job=s.claim_translations()[0];self.assertEqual(job['text'],post['text'])
        self.assertEqual(s.complete_translations([{**job,'text_de':'Der vollständige übersetzte Originaltext.'}]),1)
        self.assertEqual(s.news()[0]['text_de'],'Der vollständige übersetzte Originaltext.')
        self.assertEqual(s.news(source_id=42),[])
    def test_failed_original_fetch_does_not_present_search_snippet_as_news(self):
        self.suggestion()
        with patch.object(n,'reach',side_effect=ValueError('Unavailable')):n.hydrate_suggestions()
        self.assertEqual(s.news(),[]);self.assertEqual(n.suggestions()[0]['content_status'],'error')
    def test_german_video_is_mixed_into_its_actual_format(self):
        _,external=self.hydrate_video()
        self.assertEqual([v['id'] for v in s.feed('long')],['youtube:'+external]);self.assertEqual(s.feed('short'),[])
        self.assertTrue(s.feed('long')[0]['is_discovery']);self.assertEqual(s.sources(),[])
    def test_non_german_or_unknown_audio_language_is_not_added_to_video_feed(self):
        self.hydrate_video(language='en')
        self.assertEqual(s.feed('long'),[]);self.assertEqual(s.feed('short'),[])
        with s.db() as c:c.execute("UPDATE discovery_content SET language=''")
        self.assertEqual(s.feed('long'),[])
    def test_short_detection_requires_explicit_platform_tab_not_duration(self):
        item,_=self.suggestion('youtube')
        with patch.object(n,'video_metadata',return_value={'language':'de','language_basis':'Audiometadaten','thumbnail':'','duration':90}),\
             patch.object(n,'PUBLIC',return_value='fixture'),patch.object(n,'PARSE_TAB',side_effect=[([],{}),([{'external_id':'abcdefghijk'}],{})]):
            self.assertEqual(n.hydrate_one(item)['format'],'long')
    def test_seen_favorite_persist_and_transfer_when_creator_is_subscribed(self):
        item,external=self.hydrate_video();ident='youtube:'+external
        with s.db() as c:n.mark_discovery(c,ident,'seen',1);n.mark_discovery(c,ident,'favorite',1)
        self.assertEqual(s.feed('long'),[]);s.initialize();s.newsroom.set_settings({'enabled':True});self.assertEqual(s.feed('long'),[])
        n.feedback({'id':item['id'],'action':'subscribe'})
        source=s.sources()[0]
        s.save_success(source,[{'external_id':external,'format':'long','title':'Video','url':item['url'],'published_at':s.utc()}],{},[])
        self.assertEqual(s.feed('long'),[])
        self.assertEqual(s.feed('long',unseen=False)[0]['favorite'],1)
        self.assertFalse(s.feed('long',unseen=False)[0].get('is_discovery',False))
    def test_mute_and_disabled_discovery_remove_integrated_content(self):
        item,_=self.hydrate_video();self.assertEqual(len(s.feed('long')),1)
        n.set_settings({'enabled':False});self.assertEqual(s.feed('long'),[])
        n.set_settings({'enabled':True});self.assertEqual(len(s.feed('long')),1)
        n.feedback({'id':item['id'],'action':'mute'});self.assertEqual(s.feed('long'),[])
    def test_existing_marking_api_accepts_discovery_video_and_news(self):
        self.hydrate_video();s.TOKEN='t'*40
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/seen',data=json.dumps({'ids':['youtube:abcdefghijk']}).encode(),
              headers={'Authorization':'Bearer '+s.TOKEN,'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as r:self.assertEqual(r.status,200)
            self.assertEqual(s.feed('long'),[])
        finally:server.shutdown();server.server_close();thread.join()

    def test_favorite_discovered_video_subscribes_creator_and_preserves_content(self):
        item,external=self.hydrate_video();ident='youtube:'+external
        with s.db() as c:
            n.mark_discovery(c,ident,'favorite',1)
            creator=n.favorite_creator(c,ident)
        self.assertEqual(creator['handle'],item['handle']);self.assertEqual(len(s.sources()),1)
        video=s.feed('long')[0]
        self.assertEqual(video['id'],ident);self.assertEqual(video['favorite'],1)
        self.assertFalse(video.get('is_discovery',False))
        with s.db() as c:n.favorite_creator(c,ident)
        self.assertEqual(len(s.sources()),1)
        self.assertEqual(s.feed('long')[0]['favorite'],1)

    def test_favorite_news_api_atomically_subscribes_without_losing_translation(self):
        item,external=self.suggestion()
        with patch.object(n,'reach',return_value=[{'url':item['url'],'text':'Ein vollständiger deutscher Originalbeitrag über praktische KI.'}]):n.hydrate_suggestions()
        job=s.claim_translations()[0]
        s.complete_translations([{**job,'text_de':'Ein vollständig übersetzter Originalbeitrag.'}])
        s.TOKEN='t'*40
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(body):
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/post',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+s.TOKEN,'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as r:return json.load(r)
        try:
            with patch.object(s,'refresh',return_value=True):
                self.assertIsNone(post({'id':'discovery:'+item['id'],'seen':True})['subscribed_creator'])
                self.assertEqual(s.sources(),[])
                result=post({'id':'discovery:'+item['id'],'favorite':True})
                self.assertEqual(result['subscribed_creator']['handle'],'newcreator')
                post({'id':'discovery:'+item['id'],'favorite':True})
            self.assertEqual(len(s.sources()),1)
            news=s.news()[0]
            self.assertFalse(news.get('is_discovery',False));self.assertEqual(news['text_de'],'Ein vollständig übersetzter Originalbeitrag.')
            self.assertEqual(news['seen'],1);self.assertEqual(news['favorite'],1)
            post({'id':news['id'],'favorite':False})
            self.assertEqual(s.news()[0]['favorite'],0);self.assertEqual(len(s.sources()),1)
        finally:server.shutdown();server.server_close();thread.join()

    def test_recent_video_discovery_uses_verified_language_and_real_dates(self):
        meta={'language':'de','title':'Praktische KI-Werkzeuge','description':'Eine ausführliche Anleitung für konkrete KI-Automatisierungen.',
              'creator':'Neuer Creator','published_at':s.utc(),'channel_id':'UC'+'a'*22}
        with patch.object(n,'recent_youtube_search',return_value=[{'url':'https://www.youtube.com/watch?v=abcdefghijk'}]),patch.object(n,'video_metadata',return_value=meta):
            rows=n.collect_discovery('youtube','KI')
        result=n.candidate('youtube',rows[0],'KI')
        self.assertEqual(result['language'],'de');self.assertEqual(result['handle'],meta['channel_id'])
        self.assertIsNotNone(n.parsed_date('20261116'))

    def test_recent_search_uses_supported_filtered_youtube_url(self):
        import subprocess,urllib.parse
        result=subprocess.CompletedProcess([],0,json.dumps({'url':'https://www.youtube.com/watch?v=abcdefghijk'}),'')
        with patch.object(n.subprocess,'run',return_value=result) as command:
            self.assertEqual(len(n.recent_youtube_search('KI Tools')),1)
        args=command.call_args.args[0];url=urllib.parse.urlsplit(args[-1])
        self.assertEqual(url.hostname,'www.youtube.com');self.assertEqual(urllib.parse.parse_qs(url.query)['sp'],['CAISAhAB'])
        self.assertIn('--skip-download',args);self.assertIn('--playlist-end',args)

    def test_old_german_search_hits_do_not_use_up_the_fresh_video_quota(self):
        rows=[{'url':'https://www.youtube.com/watch?v='+f'{i:011d}'} for i in range(4)]
        base={'language':'de','title':'Praktische KI-Werkzeuge','description':'Eine ausführliche Anleitung für konkrete KI-Automatisierungen.',
              'creator':'Neuer Creator','channel_id':'UC'+'a'*22}
        metadata=[{**base,'published_at':'2020-01-01T00:00:00+00:00'} for _ in range(3)]+[{**base,'published_at':s.utc()}]
        with patch.object(n,'recent_youtube_search',return_value=rows),patch.object(n,'video_metadata',side_effect=metadata):
            found=n.collect_discovery('youtube','KI')
        self.assertEqual(len(found),1);self.assertEqual(found[0]['url'],rows[3]['url'])

    def test_tiktok_profile_search_results_are_expanded_to_real_videos(self):
        ident=str(int(time.time())<<32)
        state={'source':{'data':{'/embed/@newcreator':{'videoList':[{'id':ident,'authorUniqueId':'newcreator','desc':'Eine praktische Anleitung für neue KI-Werkzeuge.'}]}}}}
        body='<script id="__FRONTITY_CONNECT_STATE__">'+json.dumps(state)+'</script>'
        with patch.object(n,'reach',return_value=[{'url':'https://www.tiktok.com/@newcreator'}]),patch.object(n.tiktok,'profile',return_value=body),patch.object(n.tiktok,'detect_language',return_value={'language':'de','confidence':.99,'speech_heard':True}):
            rows=n.collect_discovery('tiktok','KI')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['url'],'https://www.tiktok.com/@newcreator/video/'+ident)

    def test_block_creator_hides_subscribed_videos_and_can_be_reversed(self):
        item,_=self.hydrate_video();n.feedback({'id':item['id'],'action':'subscribe'})
        source=s.sources()[0];self.assertEqual(len(s.feed('long')),1)
        n.creator_block({'source_id':source['id']})
        self.assertEqual(s.feed('long'),[]);self.assertEqual(s.sources()[0]['enabled'],0)
        self.assertEqual(n.suggestions(),[])
        n.creator_block({'platform':'youtube','handle':item['handle'],'blocked':False})
        self.assertEqual(s.sources()[0]['enabled'],1);self.assertEqual(len(s.feed('long')),1)

    def test_block_discovered_creator_prevents_stale_favorite_from_following(self):
        item,external=self.hydrate_video()
        n.creator_block({'suggestion_id':item['id']})
        self.assertEqual(s.feed('long'),[])
        with s.db() as c:self.assertIsNone(n.favorite_creator(c,'youtube:'+external))
        self.assertEqual(s.sources(),[])
        n.creator_block({'platform':'youtube','handle':item['handle'],'blocked':False})
        self.assertEqual(len(s.feed('long')),1)

if __name__=='__main__':unittest.main()
