import json,pathlib,subprocess,tempfile,time,unittest,urllib.error,wave
from unittest.mock import patch
from test_newsroom import s,n

t=n.tiktok
def body(handle='newcreator',author=None,private=False):
    video={'id':str(int(time.time())<<32),'authorUniqueId':author or handle,'desc':'Ein konkretes deutsches Tutorial über ChatGPT und KI-Werkzeuge.',
           'coverUrl':'https://example.org/cover.jpg','playAddr':'https://media.tiktok.com/public-sample.mp4'}
    state={'source':{'data':{'/embed/@'+handle:{'userInfo':{'code':200,'nickname':handle,'privateAccount':private},'videoList':[video]}}}}
    return '<script id="__FRONTITY_CONNECT_STATE__">'+json.dumps(state)+'</script>'

class TikTokDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();s.DATA=pathlib.Path(self.tmp.name);s.initialize();s.newsroom.set_settings({'enabled':True})
    def tearDown(self):self.tmp.cleanup()
    def test_profile_cache_prevents_repeat_requests_between_topics(self):
        with patch.object(t,'RAW',return_value=body()) as raw:
            first=t.profile('newcreator',budget=[2]);second=t.profile('newcreator',budget=[0])
        self.assertEqual(first,second);self.assertEqual(raw.call_count,1)
    def test_rate_limit_is_persisted_and_not_retried(self):
        error=urllib.error.HTTPError('https://www.tiktok.com/embed/@newcreator',429,'Too Many Requests',{'Retry-After':'1200'},None)
        with patch.object(t,'RAW',side_effect=error) as raw:
            with self.assertRaises(t.Paused):t.profile('newcreator')
            with self.assertRaises(t.Paused):t.profile('newcreator')
        self.assertEqual(raw.call_count,1);self.assertGreaterEqual(t.state()['cooldown_until'],time.time()+1190)
    def test_fresh_discovery_cache_remains_available_during_host_pause(self):
        cache=s.DATA/'tiktok-profile-cache';cache.mkdir()
        (cache/'newcreator.json').write_text(json.dumps({'fetched_at':time.time()-4000,'body':body()}))
        with s.db() as c:t._write(c,{'cooldown_until':time.time()+1800})
        with patch.object(t,'RAW') as raw:self.assertIn('videoList',t.profile('newcreator',max_age=21600))
        raw.assert_not_called()
    def test_profile_request_budget_does_not_block_already_cached_creators(self):
        with patch.object(t,'RAW',return_value=body()):t.profile('newcreator')
        with patch.object(t,'RAW') as raw:
            self.assertTrue(t.profile('newcreator',budget=[0]))
            with self.assertRaises(t.Paused):t.profile('othercreator',budget=[0])
        raw.assert_not_called()
    def test_one_failed_profile_does_not_drop_another_verified_creator(self):
        urls=[{'url':'https://www.tiktok.com/@newcreator'},{'url':'https://www.tiktok.com/@othercreator'}]
        with patch.object(t,'profile',side_effect=[body(),t.Paused('Pause')]),patch.object(t,'detect_language',return_value={'language':'de','confidence':.99,'speech_heard':True}):rows=t.discover_items(urls,lambda h:True)
        self.assertEqual(len(rows),1);self.assertIn('/@newcreator/video/',rows[0]['url'])
    def test_private_profiles_and_wrong_authors_are_not_published(self):
        with self.assertRaises(ValueError):t.parse_profile(body(private=True),'newcreator')
        with patch.object(t,'profile',return_value=body(author='someoneelse')):
            self.assertEqual(t.discover_items([{'url':'https://www.tiktok.com/@newcreator'}],lambda h:True),[])
    def test_audio_language_not_description_controls_german_eligibility(self):
        item={'handle':'newcreator','url':'https://www.tiktok.com/@newcreator/video/'+str(int(time.time())<<32),'title':'Deutsche Beschreibung'}
        with patch.object(t,'profile',return_value=body()),patch.object(t,'detect_language',return_value={'language':'en','confidence':.99,'speech_heard':True}):
            self.assertEqual(t.hydrate(item)['status'],'language_unconfirmed')
        with patch.object(t,'profile',return_value=body()),patch.object(t,'detect_language',return_value={'language':'de','confidence':.99,'speech_heard':True}):
            self.assertNotIn('status',t.hydrate(item));self.assertEqual(t.hydrate(item)['format'],'short')
    def test_language_output_requires_probability_and_actual_recognized_speech(self):
        proof=t.parse_language_result({'transcription':[{'text':'Das ist eine verständliche deutsche Hörprobe.'}]},'auto-detected language: de (p = 0.992623)')
        self.assertTrue(proof['speech_heard']);self.assertEqual(proof['language'],'de')
        self.assertFalse(t.parse_language_result({'transcription':[]},'auto-detected language: de (p = 0.99)')['speech_heard'])
        with self.assertRaises(ValueError):t.parse_language_result({},'no language metadata')
    def test_non_german_audio_is_rejected_before_recommendation_selection(self):
        with patch.object(t,'profile',return_value=body()),patch.object(t,'detect_language',return_value={'language':'en','confidence':.99,'speech_heard':True}):
            self.assertEqual(t.discover_items([{'url':'https://www.tiktok.com/@newcreator'}],lambda h:True),[])
    def test_local_probe_is_cached_and_temporary_audio_is_removed(self):
        runtime=s.DATA/'tiktok-language';runtime.mkdir()
        (runtime/'whisper-cli').touch();(runtime/'ggml-tiny-q5_1.bin').touch()
        directories=[]
        def run(args,**kw):
            if '-i' in args:
                target=pathlib.Path(args[-1]);directories.append(target.parent)
                with wave.open(str(target),'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\x01\x00'*16000*12)
                return subprocess.CompletedProcess(args,0,b'',b'')
            target=pathlib.Path(args[args.index('-of')+1]).with_suffix('.json')
            target.write_text(json.dumps({'transcription':[{'text':'Das ist eine verständliche deutsche Hörprobe.'}]}))
            return subprocess.CompletedProcess(args,0,'','auto-detected language: de (p = 0.99)')
        video={'id':'7708862005712620833','playAddr':'https://media.tiktok.com/public-sample.mp4'}
        with patch.object(t,'_ffmpeg',return_value='ffmpeg'),patch.object(t.subprocess,'run',side_effect=run) as called:
            proof=t.detect_language(video);self.assertEqual(proof['language'],'de')
            t.detect_language(video);self.assertEqual(called.call_count,2)
        self.assertTrue(all(not p.exists() for p in directories))
        cached=(s.DATA/'tiktok-language-results'/('7708862005712620833.json')).read_text()
        self.assertNotIn('verständliche',cached);self.assertNotIn('audio',cached)
    def test_ffmpeg_lookup_uses_codys_isolated_reach_home(self):
        binary=s.DATA/'ffmpeg';binary.touch()
        result=subprocess.CompletedProcess([],0,str(binary)+'\n','')
        with patch('shutil.which',return_value=None),patch.object(t.subprocess,'run',return_value=result) as command:
            self.assertEqual(t._ffmpeg(),str(binary))
        self.assertEqual(command.call_args.kwargs['env']['HOME'],str(s.DATA/'reach'))
    def test_same_manual_verification_build_is_not_duplicated(self):
        with patch.object(n,'collect_discovery',return_value=[]):n.discover(force=True,platforms=['tiktok']);n.discover(force=True,platforms=['tiktok'])
        self.assertEqual(len(n.discovery_status()['runs']),1)

if __name__=='__main__':unittest.main()
