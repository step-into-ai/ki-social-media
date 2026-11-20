"""Deterministic real-Chromium scroll check on a local synthetic page; no platform accounts."""
import json,pathlib,sys,os
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'collector'))
import browser_discovery as b
from agent_reach.runtime import browser,cdp

def main():
    for key in ('CODY_API_TOKEN','CODY_TRANSLATOR_TOKEN','CODY_SPEECH_TOKEN','AI_API_KEY','SPEECH_API_KEY'):os.environ.pop(key,None)
    browser.ensure_running()
    target=(cdp.call('Target.createTarget',{'url':'about:blank'}) or {})['targetId']
    class FixtureSession(b.Session):
        def __init__(self):self.target=target;self.cdp=cdp;self.browser=browser;self.platform='x'
        def snapshot(self):
            state=super().snapshot();state['url']='https://x.com/home';return state
        def reject_optional_cookies(self):return False
    try:
        session=FixtureSession();session.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
        frame=session.call('Page.getFrameTree')['frameTree']['frame']['id']
        cards=''.join('<article data-testid="tweet" style="height:260px;border:1px solid gray"><a href="https://x.com/example/status/'+str(2120000000000000000+i)+'">fixture link</a><div data-testid="tweetText">Synthetic AI workflow and CAPTCHA discussion example '+str(i)+'</div></article>' for i in range(24))
        hidden='<article data-testid="tweet" style="display:none"><a href="https://x.com/example/status/2129999999999999999">hidden fixture</a></article>'
        session.call('Page.setDocumentContent',{'frameId':frame,'html':'<!doctype html><html><body>'+cards+hidden+'</body></html>'})
        result=b.scan_loop(session,'x','fixture',max_steps=3,max_seconds=30,dwell=1)
        assert result['metrics']['status']=='ok' and result['metrics']['scroll_steps']==3
        assert result['metrics']['new_items_after_scroll']>0
        assert not any('2129999999999999999' in row['url'] for row in result['items'])
        print(json.dumps({'real_chromium_fixture_passed':True,'scroll_steps':result['metrics']['scroll_steps'],'new_visible_cards':result['metrics']['new_items_after_scroll']}))
    finally:cdp.call('Target.closeTarget',{'targetId':target})

if __name__=='__main__':main()
