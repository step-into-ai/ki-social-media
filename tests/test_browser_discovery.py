import datetime,importlib.util,json,pathlib,subprocess,tempfile,time,unittest
from unittest.mock import patch
from test_newsroom import s,n

b=n.browser_discovery
def post(number,text='A useful concrete public explanation of AI automation and tools.'):
    return {'url':'https://x.com/newcreator/status/'+str(number),'text':text}
def snapshot(rows,offset=0,**extra):
    return {'url':'https://x.com/home','items':rows,'scroll':offset,'viewport':{'width':1280,'height':900},'status':200,**extra}
class FakeSession:
    def __init__(self,frames):self.frames=frames;self.index=0;self.wheels=0
    def snapshot(self):
        frame=self.frames[min(self.index,len(self.frames)-1)];self.index+=1;return frame
    def wheel(self,viewport):self.wheels+=1
    def reject_optional_cookies(self):return False
    def screenshot(self,path):raise AssertionError('No screenshots requested by this test')

class BrowserLoopTests(unittest.TestCase):
    def scan(self,frames,steps=6):
        session=FakeSession(frames);clock=[0.]
        result=b.scan_loop(session,'x','KI',steps,60,clock=lambda:clock[0],sleep=lambda sec:clock.__setitem__(0,clock[0]+sec))
        return result,session
    def test_actual_new_viewport_items_and_scroll_steps_are_recorded(self):
        result,session=self.scan([snapshot([post(2120000000000000001)]),snapshot([post(2120000000000000002)],700),snapshot([post(2120000000000000003)],1400)],steps=2)
        self.assertEqual(result['metrics']['status'],'ok');self.assertEqual(session.wheels,2)
        self.assertEqual(result['metrics']['new_items_after_scroll'],2)
        self.assertEqual({p['raw']['observed_step'] for p in result['items']},{0,1,2})
    def test_challenge_login_and_rate_limits_stop_without_scrolling(self):
        for extra in ({'challenge':True},{'login':True},{'status':429}):
            result,session=self.scan([snapshot([],**extra)])
            self.assertEqual(session.wheels,0);self.assertEqual(result['metrics']['status'],'blocked')
    def test_scrolling_a_page_without_posts_is_not_reported_as_success(self):
        # A consent/text page moving is not evidence that content was actually seen.
        result,session=self.scan([snapshot([],i*700) for i in range(12)],steps=2)
        self.assertEqual(result['metrics']['status'],'no_new_content');self.assertEqual(result['metrics']['items_observed'],0)
    def test_unchanged_feed_stops_early(self):
        result,session=self.scan([snapshot([post(2120000000000000001)])])
        self.assertEqual(session.wheels,2);self.assertEqual(result['metrics']['stop_reason'],'feed_unchanged')
    def test_feed_urls_and_candidates_reject_other_hosts_and_credentials(self):
        self.assertEqual(b.entry_url('x','untrusted topic'),'https://x.com/home')
        self.assertEqual(b.entry_url('tiktok','KI'),'https://www.tiktok.com/')
        self.assertTrue(b.entry_url('youtube','KI').startswith('https://www.youtube.com/hashtag/'))
        for url in ('https://x.com.evil.test/a/status/2120000000000000001','http://x.com/a/status/2120000000000000001','https://u:p@x.com/a/status/2120000000000000001','https://x.com/i/status/2120000000000000001'):
            self.assertIsNone(b.canonical_item('x',{'url':url,'text':'A substantial text'}))
    def test_no_unexpected_site_is_read_or_scrolled(self):
        result,session=self.scan([snapshot([],url='https://example.org/private')])
        self.assertEqual(result['metrics']['stop_reason'],'unexpected_navigation');self.assertEqual(session.wheels,0)

class BrowserPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();s.DATA=pathlib.Path(self.tmp.name);s.initialize()
        with s.db() as c:c.execute('DELETE FROM sources')
        n.set_settings({'enabled':True})
        self.env=patch.dict(n.os.environ,{'CODY_BROWSER_DISCOVERY':'true'});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def payload(self,reason=None):
        ident=((int(time.time()*1000)-1288834974657)<<22)
        return {'items':[post(ident)],'metrics':{'id':'a'*32,'status':'blocked' if reason else 'ok','stop_reason':reason or 'step_limit',
          'platform':'x','topic':'KI','scroll_steps':0 if reason else 3,'viewport_changed':reason is None,'new_items_after_scroll':0 if reason else 1,'items_observed':1}}
    def process(self,data):return subprocess.CompletedProcess([],0,json.dumps(data),'')
    def test_browser_candidates_have_provenance_and_same_batch_does_not_rescan(self):
        with patch.dict(n.os.environ,{'CODY_API_TOKEN':'fixture-owner-secret','AI_API_KEY':'fixture-provider-secret'}),patch.object(n.subprocess,'run',return_value=self.process(self.payload())) as command:
            first=n.collect_discovery('x','KI');second=n.collect_discovery('x','Automatisierung')
        self.assertEqual(command.call_count,1);self.assertEqual(first,second)
        candidate=n.candidate('x',first[0],'KI')
        self.assertEqual(candidate['discovered_via'],'browser_scroll');self.assertEqual(candidate['browser_scan_id'],'a'*32)
        self.assertEqual(len(n.discovery_status()['browser']['recent_scans']),1)
        self.assertNotIn('CODY_API_TOKEN',command.call_args.kwargs['env'])
        self.assertNotIn('AI_API_KEY',command.call_args.kwargs['env'])
    def test_fallback_is_explicit_and_is_not_labelled_browser_content(self):
        with patch.object(n.subprocess,'run',return_value=self.process(self.payload('challenge'))),patch.object(n,'reach',return_value=[post(((int(time.time()*1000)-1288834974657)<<22))]):
            rows=n.collect_discovery('x','KI')
        self.assertEqual(n.candidate('x',rows[0],'KI')['discovered_via'],'index')
        self.assertEqual(n.discovery_status()['browser']['recent_scans'][0]['status'],'blocked')
        self.assertTrue(n.discovery_status()['browser']['recent_scans'][0]['search_fallback_used'])
    def test_human_handoff_never_triggers_search_fallback(self):
        with patch.object(n.subprocess,'run',return_value=self.process(self.payload('human_control_active'))),patch.object(n,'reach') as search:
            for _ in range(2):
                with self.assertRaises(ValueError):n.collect_discovery('x','KI')
            search.assert_not_called()
    def test_browser_disabled_does_not_start_a_browser(self):
        with patch.dict(n.os.environ,{'CODY_BROWSER_DISCOVERY':'false'}),patch.object(n.subprocess,'run') as command:
            self.assertIsNone(n.collect_browser('x','KI'));command.assert_not_called()
    def test_unrelated_tiktok_cards_do_not_spend_profile_and_audio_budget(self):
        data=self.payload();data['items']=[{'url':'https://www.tiktok.com/@gamingcreator/video/7707609074547952928','text':'A racing game and a city map comparison'}];data['metrics']['platform']='tiktok'
        with patch.object(n.subprocess,'run',return_value=self.process(data)),patch.object(n.tiktok,'hydrate') as audio:
            self.assertIsNone(n.collect_browser('tiktok','KI'));audio.assert_not_called()
        self.assertTrue(n.discovery_status()['browser']['recent_scans'][0]['search_fallback_used'])
    def test_active_human_handoff_does_not_launch_any_browser(self):
        (s.DATA/'browser-handoff.active').write_text(json.dumps({'expires_at':time.time()+600}))
        with patch.object(n.subprocess,'run') as command,patch.object(n,'reach') as search:
            with self.assertRaises(ValueError):n.collect_discovery('x','KI')
            command.assert_not_called();search.assert_not_called()
    def test_finished_handoff_file_removal_does_not_pause_source_collection(self):
        with patch.object(pathlib.Path,'is_file',return_value=True),patch.object(pathlib.Path,'read_text',side_effect=FileNotFoundError):
            self.assertFalse(n.browser_handoff_active())

if __name__=='__main__':unittest.main()
