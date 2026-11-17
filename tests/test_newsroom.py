import importlib.util,json,pathlib,tempfile,threading,time,unittest,urllib.request,urllib.error,datetime as dt
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('editorial_service',pathlib.Path(__file__).parents[1]/'collector/service.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
n=s.newsroom

RSS=b'''<rss version="2.0"><channel><title>Example News</title><item><guid>one</guid><title>AI update</title>
<link>https://example.org/story?utm_source=feed</link><description>&lt;p&gt;A substantive new tool for automation.&lt;/p&gt;&lt;script&gt;bad()&lt;/script&gt;</description>
<pubDate>Mon, 16 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'''
ATOM=b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom News</title><entry><id>tag:example,1</id><title>Update</title>
<link rel="alternate" href="https://example.org/atom"/><updated>2026-11-16T12:00:00Z</updated><summary>A real feed summary.</summary></entry></feed>'''

class NewsroomTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();s.DATA=pathlib.Path(self.tmp.name);s.initialize();s.AI_ENABLED=True;s.newsroom.set_settings({'enabled':True})
        with s.db() as c:c.execute('DELETE FROM sources')
    def tearDown(self):self.tmp.cleanup()
    def source(self,platform='rss',handle='https://example.org/rss',delivery='news'):
        with s.db() as c:
            ident=c.execute('INSERT INTO sources(platform,handle,title,mode,delivery) VALUES(?,?,?,?,?)',
                            (platform,handle,'Example','posts' if platform=='rss' else 'both',delivery)).lastrowid
        with s.db() as c:return dict(c.execute('SELECT * FROM sources WHERE id=?',(ident,)).fetchone())
    def video(self,source):
        s.save_success(source,[{'external_id':'abcdefghijk','format':'long','title':'An automation tutorial',
          'url':'https://www.youtube.com/watch?v=abcdefghijk','published_at':'2026-11-16T12:00:00Z'}],{},[])
        return 'youtube:abcdefghijk'
    def sample(self,platform='x',handle='newcreator'):
        return {'id':'candidate1','platform':platform,'handle':handle,'creator':'New Creator','profile_url':'https://x.com/'+handle,
          'url':'https://x.com/'+handle+'/status/1234567890123456789','title':'A useful AI automation tool',
          'evidence':'A concrete tutorial about useful AI automation tools.','published_at':s.utc(),'topic':'KI','basis':'Beitragstext'}
    def discovery_job(self,items):
        payload=json.dumps({'candidates':items,'topics':['KI'],'exclude':[],'limit':3})
        with s.db() as c:
            ident=c.execute("INSERT INTO discovery_runs(slot,started_at,status,input_json,input_hash) VALUES('test',?,'queued',?,'hash')",(s.utc(),payload)).lastrowid
        return n.claim_jobs()[0]
    def test_rss_and_atom_preserve_real_dates_strip_html_and_tracking(self):
        rows,meta=n.parse_feed(RSS,'https://example.org/rss')
        self.assertEqual(meta['title'],'Example News');self.assertEqual(rows[0]['url'],'https://example.org/story')
        self.assertNotIn('bad()',rows[0]['text']);self.assertEqual(rows[0]['published_at'],'2026-11-16T12:00:00+00:00')
        atom,_=n.parse_feed(ATOM,'https://example.org/rss');self.assertEqual(atom[0]['url'],'https://example.org/atom')
        self.assertEqual(atom[0]['published_at'],rows[0]['published_at'])
    def test_rss_retry_keeps_seen_and_date_and_invalidates_changed_translation(self):
        source=self.source();rows,meta=n.parse_feed(RSS,'https://example.org/rss');rows[0]['published_at']=None
        s.save_success(source,rows,meta,[])
        with s.db() as c:c.execute("UPDATE posts SET seen=1,favorite=1,text_de='Deutscher Text',translation_status='ready'")
        before=s.posts()[0];s.save_success(source,rows,meta,[]);after=s.posts()[0]
        self.assertEqual(after['published_at'],before['published_at']);self.assertEqual(after['seen'],1);self.assertEqual(after['favorite'],1)
        self.assertEqual(after['text_de'],'Deutscher Text');self.assertEqual(after['date_known'],0)
        rows[0]['text']='Changed original';s.save_success(source,rows,meta,[])
        self.assertEqual(s.posts()[0]['text_de'],'');self.assertEqual(s.posts()[0]['translation_status'],'pending')
    def test_rss_duplicate_url_does_not_fill_news_twice(self):
        rows,meta=n.parse_feed(RSS,'https://example.org/rss')
        s.save_success(self.source(),rows,meta,[]);s.save_success(self.source(handle='https://second.example/rss'),rows,meta,[])
        self.assertEqual(len(s.posts()),2);self.assertEqual(len(s.news()),1)
    def test_private_dns_credentials_and_xml_entities_are_rejected(self):
        for address in ['127.0.0.1','10.1.2.3','169.254.169.254','::1','fd00::1']:
            with patch.object(n.socket,'getaddrinfo',return_value=[(2,1,6,'',(address,443))]):
                with self.assertRaises(ValueError):n.public_url('https://example.org/rss')
        for url in ['http://example.org/rss','https://user:pass@example.org/rss','https://example.org:443/rss','https://example.tail000000.ts.net/rss']:
            with self.assertRaises(ValueError):n.public_url(url)
        with self.assertRaises(ValueError):n.parse_feed(b'<!DOCTYPE x [<!ENTITY y "test">]><rss/>','https://example.org/rss')
    def test_redirect_to_internal_network_is_not_followed(self):
        class Response:
            status=302
            def getheader(self,*args):return 'https://127.0.0.1/private'
        with patch.object(n.socket,'getaddrinfo',side_effect=[[(2,1,6,'',('1.1.1.1',443))],[(2,1,6,'',('127.0.0.1',443))]]),\
             patch.object(n.http.client.HTTPSConnection,'request'),patch.object(n.http.client.HTTPSConnection,'getresponse',return_value=Response()):
            with self.assertRaises(ValueError):n.fetch_feed('https://example.org/rss')
    def test_video_delivery_is_independent_of_format_and_summary_requires_real_transcript(self):
        source=self.source('youtube','creator');ident=self.video(source)
        self.assertEqual(s.feed('long'),[])
        with patch.object(n,'reach',return_value=[{'text':'A real full transcript with meaningful contents. '*8}]):n.prepare_summaries()
        job=n.claim_jobs()[0];self.assertEqual(job['kind'],'summary');self.assertIn('real full transcript',job['text'])
        result={**{k:job[k] for k in ('id','kind','text_hash')},'text_de':'Eine sachliche deutsche Nachricht aus dem Video-Transkript. '*5}
        self.assertEqual(n.complete_job(result),1);self.assertEqual(len(s.news()),1)
        self.assertEqual(s.news()[0]['kind'],'video_summary')
        with s.db() as c:c.execute("UPDATE sources SET delivery='both'")
        self.assertEqual(len(s.feed('long')),1)
        with s.db() as c:c.execute('UPDATE videos SET seen=1')
        self.assertEqual(s.news(unseen=True),[])
        result['text_hash']='stale';self.assertEqual(n.complete_job(result),0)
    def test_missing_transcript_never_becomes_a_fake_summary(self):
        source=self.source('youtube','creator');self.video(source)
        with patch.object(n,'reach',side_effect=ValueError('Transkript fehlt.')):n.prepare_summaries()
        self.assertEqual(n.summary_status()[0]['status'],'awaiting_speech');self.assertEqual(n.claim_jobs(),[]);self.assertEqual(s.news(),[])
    def test_whisper_transcript_lease_and_summary_provenance(self):
        source=self.source('youtube','creator');ident=self.video(source);n.queue_summary(ident)
        with s.db() as c:c.execute("UPDATE summaries SET status='awaiting_speech'")
        job=n.claim_speech()[0];self.assertEqual(n.claim_speech(),[])
        result={'id':ident,'lease':'stale','text':'An actual Whisper transcript. '*10,'provider':'openai'}
        self.assertEqual(n.complete_speech(result),0)
        result['lease']=job['lease'];self.assertEqual(n.complete_speech(result),1)
        editorial=n.claim_jobs()[0]
        n.complete_job({**{k:editorial[k] for k in ('id','kind','text_hash')},'text_de':'Eine Nachricht aus dem tatsächlichen Whisper-Transkript. '*4})
        self.assertEqual(s.news()[0]['basis'],'Audiospur, konfigurierte Spracherkennung (openai)')
    def test_existing_compatible_speech_uses_its_own_provenance(self):
        source=self.source('youtube','creator');ident=self.video(source);n.queue_summary(ident)
        n.set_speech_status({'available':True,'provider':'compatible'})
        self.assertEqual(n.speech_status()['provider'],'compatible')
        with s.db() as c:c.execute("UPDATE summaries SET status='awaiting_speech'")
        job=n.claim_speech()[0]
        self.assertEqual(n.complete_speech({**job,'text':'An actual complete compatible audio transcript. '*8,'provider':'compatible'}),1)
        with s.db() as c:row=c.execute('SELECT basis,status FROM summaries WHERE video_id=?',(ident,)).fetchone()
        self.assertEqual(row['basis'],'Audiospur, konfigurierte Spracherkennung (compatible)');self.assertEqual(row['status'],'queued')
    def test_failed_audio_does_not_publish_partial_transcript(self):
        source=self.source('youtube','creator');ident=self.video(source);n.queue_summary(ident)
        with s.db() as c:c.execute("UPDATE summaries SET status='awaiting_speech'")
        job=n.claim_speech()[0];n.complete_speech({**job,'error':True})
        self.assertEqual(n.claim_speech(),[]);self.assertEqual(s.news(),[])
    def test_discovery_settings_reject_excessive_frequency_or_invalid_platform(self):
        for body in [{'runs_per_day':3},{'max_suggestions':4},{'platforms':['facebook']},{'topics':[]},{'enabled':'yes'}]:
            with self.assertRaises(ValueError):n.set_settings(body)
        result=n.set_settings({'topics':['KI','KI'],'exclude':['Werbung'],'runs_per_day':1})
        self.assertEqual(result['topics'],['KI']);self.assertEqual(result['runs_per_day'],1)
    def test_discovery_filters_followed_muted_and_excluded_creators(self):
        item=self.sample();config=n.settings()
        with s.db() as c:self.assertTrue(n.allowed_candidate(c,item,config))
        self.source('x',item['handle'])
        with s.db() as c:self.assertFalse(n.allowed_candidate(c,item,config));c.execute('DELETE FROM sources')
        with s.db() as c:c.execute('INSERT INTO muted_creators(platform,handle) VALUES(?,?)',('x',item['handle']))
        with s.db() as c:self.assertFalse(n.allowed_candidate(c,item,config));c.execute('DELETE FROM muted_creators')
        with s.db() as c:self.assertFalse(n.allowed_candidate(c,item,{**config,'exclude':['automation']}))
    def test_hallucinated_recommendation_ids_rejected_and_feedback_preserved(self):
        job=self.discovery_job([self.sample()])
        result={**{k:job[k] for k in ('id','kind','text_hash')},'selections':[{'id':'invented','reason':'An invented recommendation is not evidence.'}]}
        with self.assertRaises(ValueError):n.complete_job(result)
        result['selections'][0]['id']='candidate1';self.assertEqual(n.complete_job(result),1)
        self.assertEqual(len(n.suggestions()),1)
        n.feedback({'id':'candidate1','action':'mute'});self.assertEqual(n.suggestions(),[])
        with s.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM muted_creators').fetchone()[0],1)
    def test_suggestion_subscription_is_explicit_and_idempotent(self):
        job=self.discovery_job([self.sample()])
        n.complete_job({**{k:job[k] for k in ('id','kind','text_hash')},'selections':[{'id':'candidate1','reason':'A concrete explanation of a useful AI automation workflow.'}]})
        self.assertEqual(s.sources(),[])
        n.feedback({'id':'candidate1','action':'subscribe'});n.feedback({'id':'candidate1','action':'subscribe'})
        self.assertEqual(len(s.sources()),1);self.assertEqual(s.sources()[0]['handle'],'newcreator');self.assertEqual(n.suggestions(),[])
    def test_restart_does_not_duplicate_discovery_slot(self):
        with patch.object(n,'collect_discovery',return_value=[] ) as collect:
            n.discover();first=collect.call_count;s.initialize();s.AI_ENABLED=True;s.newsroom.set_settings({'enabled':True});n.discover()
            self.assertEqual(collect.call_count,first)
        self.assertEqual(len(n.discovery_status()['runs']),1)
    def test_old_candidates_are_rejected_and_x_date_is_not_search_time(self):
        old={'url':'https://x.com/creator/status/1500000000000000000','text':'A sufficiently long old public post about AI.'}
        self.assertIsNone(n.candidate('x',old,'KI'))
        undated={'url':'https://www.youtube.com/watch?v=abcdefghijk','title':'A sufficiently long video title about AI','raw':{'channel_id':'UC'+'a'*22}}
        self.assertIsNone(n.candidate('youtube',undated,'KI'))
    def test_x_search_internal_url_uses_explicit_scraped_username(self):
        snowflake=str((int(time.time()*1000)-1288834974657)<<22)
        item={'url':'https://x.com/i/status/'+snowflake,'author':'Display Name',
              'text':'A real public post with useful details on practical AI tools.', 'raw':{'author':'RealCreator'}}
        result=n.candidate('x',item,'KI')
        self.assertEqual(result['handle'],'realcreator');self.assertEqual(result['profile_url'],'https://x.com/realcreator')
        self.assertEqual(result['url'],'https://x.com/realcreator/status/'+snowflake)
        item['raw']={};self.assertIsNone(n.candidate('x',item,'KI'))
    def test_summary_claim_recovers_after_worker_lease_expires(self):
        source=self.source('youtube','creator');ident=self.video(source);n.queue_summary(ident)
        with s.db() as c:c.execute("UPDATE summaries SET status='working',transcript='actual transcript',text_hash='hash',next_at=?",(time.time()+200,))
        self.assertEqual(n.claim_jobs(),[])
        with s.db() as c:c.execute('UPDATE summaries SET next_at=0')
        self.assertEqual(n.claim_jobs()[0]['text'],'actual transcript')
    def test_news_endpoints_are_authenticated_and_translator_cannot_change_settings(self):
        s.TOKEN='t'*40;s.TRANSLATOR_TOKEN='r'*40;s.SPEECH_TOKEN='s'*40
        server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def req(path,body=None,token=''):
            return urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
              headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}))
        try:
            for path in ['/api/news','/api/discovery','/api/summaries','/api/suggestions']:
                with self.assertRaises(urllib.error.HTTPError) as e:req(path)
                self.assertEqual(e.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as e:req('/api/discovery',{'enabled':False},s.TRANSLATOR_TOKEN)
            self.assertEqual(e.exception.code,401)
            with req('/api/discovery',{'enabled':False},s.TOKEN) as r:self.assertFalse(json.load(r)['settings']['enabled'])
            with self.assertRaises(urllib.error.HTTPError) as e:req('/internal/editorial/claim',{},s.TOKEN)
            self.assertEqual(e.exception.code,401)
            with req('/internal/editorial/claim',{},s.TRANSLATOR_TOKEN) as r:self.assertEqual(json.load(r)['jobs'],[])
            with self.assertRaises(urllib.error.HTTPError) as e:req('/internal/speech/claim',{},s.TOKEN)
            self.assertEqual(e.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as e:req('/internal/editorial/claim',{},s.SPEECH_TOKEN)
            self.assertEqual(e.exception.code,401)
            with req('/internal/speech/status',{'available':False},s.SPEECH_TOKEN) as r:self.assertEqual(r.status,200)
            self.assertFalse(n.speech_status()['available'])
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
