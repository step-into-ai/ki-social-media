"""Bounded, read-only scrolling of rendered platform feeds in the owned Agent Reach browser."""
from __future__ import annotations
import argparse,base64,contextlib,datetime,hashlib,io,json,os,pathlib,re,time,urllib.parse,uuid

PLATFORMS={'youtube':{'www.youtube.com','youtube.com','consent.youtube.com'},
           'tiktok':{'www.tiktok.com','tiktok.com'},'x':{'x.com','www.x.com','twitter.com','www.twitter.com'}}

class BrowserError(ValueError):
    def __init__(self,code):self.code=code;super().__init__(code)

def bounded(value,default,low,high):
    try:return max(low,min(high,int(value)))
    except (ValueError,TypeError):return default

def entry_url(platform,topic):
    if platform not in PLATFORMS:raise BrowserError('unsupported_platform')
    if platform=='x':return 'https://x.com/home'
    if platform=='tiktok':return 'https://www.tiktok.com/'
    tag={'KI':'künstlicheintelligenz','praktische KI-Werkzeuge':'chatgpt'}.get(topic,topic)
    tag=re.sub(r'[^\w]','',tag.casefold())[:80]
    if not tag:raise BrowserError('empty_topic')
    return ('https://www.youtube.com/hashtag/' if platform=='youtube' else 'https://www.tiktok.com/tag/')+urllib.parse.quote(tag,safe='')

def canonical_item(platform,row):
    if not isinstance(row,dict):return None
    try:p=urllib.parse.urlsplit(str(row.get('url','')))
    except ValueError:return None
    if p.scheme!='https' or p.hostname not in PLATFORMS[platform] or p.username or p.password or p.port:return None
    if platform=='x':
        m=re.fullmatch(r'/([A-Za-z0-9_]{1,15})/status/(\d{15,25})(?:/photo/\d+|/video/\d+)?',p.path)
        if not m or m[1].lower() in ('i','home','search','explore','intent'):return None
        url='https://x.com/'+m[1]+'/status/'+m[2];raw={'author':m[1]}
    elif platform=='tiktok':
        m=re.fullmatch(r'/@([A-Za-z0-9_.]{2,24})/video/(\d{15,25})',p.path)
        if not m:return None
        url='https://www.tiktok.com/@'+m[1]+'/video/'+m[2];raw={}
    else:
        ident=urllib.parse.parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else p.path.removeprefix('/shorts/') if p.path.startswith('/shorts/') else ''
        if not re.fullmatch(r'[\w-]{11}',ident):return None
        url='https://www.youtube.com/watch?v='+ident;raw={}
    text=str(row.get('text') or row.get('title') or '').strip()[:5000]
    if len(text)<10:return None
    return {'url':url,'text':text,'title':str(row.get('title') or text[:160])[:500],
            'author':str(row.get('author') or raw.get('author',''))[:200],'raw':raw}

# Only DOM content that intersects the viewport and is not covered by an overlay counts.
SNAPSHOT=r'''(platform=>{
 const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);
  if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0'||r.width<2||r.height<2||r.bottom<=0||r.top>=innerHeight||r.right<=0||r.left>=innerWidth)return false;
  const x=Math.max(1,Math.min(innerWidth-2,(Math.max(0,r.left)+Math.min(innerWidth,r.right))/2));
  const y=Math.max(1,Math.min(innerHeight-2,(Math.max(0,r.top)+Math.min(innerHeight,r.bottom))/2));
  const top=document.elementFromPoint(x,y);return !!top&&(e.contains(top)||top.contains(e));};
 const text=document.body?.innerText||'',items=[],seen=new Set();
 let anchors=[];
 if(platform==='x'){
  for(const card of document.querySelectorAll('article[data-testid="tweet"],article')){
   if(!visible(card))continue;
   const a=[...card.querySelectorAll('a[href*="/status/"]')].find(a=>/\/status\/\d+$/.test(new URL(a.href).pathname));
   if(!a)continue;
   items.push({url:a.href,text:(card.querySelector('[data-testid="tweetText"]')?.innerText||card.innerText).slice(0,5000)});
  }
 } else if(platform==='tiktok') {
  for(const card of document.querySelectorAll('article[data-e2e="recommend-list-item-container"],article[data-scroll-index]')){
   if(!visible(card))continue;
   const id=card.querySelector('[data-more-menu-item-id]')?.getAttribute('data-more-menu-item-id')||card.getAttribute('data-item-id')||'';
   const authorLink=card.querySelector('a[data-e2e="video-author-avatar"][href],a[href^="/@"]');
   let handle='';try{handle=new URL(authorLink?.href||'',location.origin).pathname.match(/^\/@([A-Za-z0-9_.]{2,24})\/?$/)?.[1]||'';}catch(e){}
   if(!/^\d{15,25}$/.test(id)||!handle)continue;
   items.push({url:'https://www.tiktok.com/@'+handle+'/video/'+id,author:handle,text:card.innerText.slice(0,5000),title:card.innerText.slice(0,180)});
  }
 } else {
  anchors=[...document.querySelectorAll(platform==='youtube'?'a[href*="watch?v="],a[href^="/shorts/"]':'a[href*="/video/"]')];
  for(const a of anchors){
   const card=a.closest(platform==='youtube'?'ytd-rich-item-renderer,ytd-video-renderer,yt-lockup-view-model,ytd-grid-video-renderer,yt-shorts-lockup-view-model':'[data-e2e="user-post-item"],[data-e2e="challenge-item"],[data-e2e*="recommend-list-item"],article')||a;
   if(!visible(card)||seen.has(a.href))continue;seen.add(a.href);
   const image=card.querySelector('img');
   items.push({url:a.href,title:(card.querySelector('#video-title,h3,h2')?.innerText||a.getAttribute('title')||a.innerText||image?.alt||card.innerText).slice(0,500),
     text:(card.innerText||image?.alt||a.getAttribute('aria-label')||'').slice(0,5000)});
   if(items.length>=30)break;
  }
 }
 const dialog=[...document.querySelectorAll('[role="dialog"],dialog')].filter(visible).map(e=>e.innerText).join('\n');
 const password=!![...document.querySelectorAll('input[type="password"]')].find(visible);
 const gated=items.length===0&&(/log in to continue|sign in to continue|melde dich an|anmelden, um/i.test(dialog)||password||/\/i\/flow\/login|\/login\b/.test(location.pathname));
 const gateText=dialog||(items.length===0?text.slice(0,3500):'');
 const challenge=/verify you are human|sicherheitsüberprüfung|verify to continue|captcha|drag the puzzle|complete the puzzle/i.test(gateText)
  ||[...document.querySelectorAll('iframe[src*="captcha"],#captcha_container')].some(visible);
 const scrolls=[...document.querySelectorAll('main,[role="main"],[role="feed"],div')].slice(0,2000).filter(visible).map(e=>e.scrollTop||0);
 return {url:location.href,title:document.title,items:items.slice(0,30),scroll:Math.max(scrollY,...scrolls,0),
  viewport:{width:innerWidth,height:innerHeight},status:performance.getEntriesByType('navigation')[0]?.responseStatus||0,
  login:gated,challenge,consent:location.hostname==='consent.youtube.com',
  body_excerpt:items.length? '':text.slice(0,180)};
})'''

CONSENT=r'''(()=>{
 if(location.hostname!=='consent.youtube.com'&&!/cookie/i.test(document.body?.innerText||''))return false;
 const names=new Set(['reject all','alle ablehnen','decline all','refuse non-essential cookies','nicht erforderliche cookies ablehnen','nur notwendige cookies']);
 const button=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].find(e=>{
  const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&!e.closest('article,[data-testid="tweet"]')&&names.has((e.innerText||e.getAttribute('aria-label')||e.value||'').trim().toLowerCase());});
 if(!button)return false;button.scrollIntoView({block:'center'});button.click();return true;
})()'''

class Session:
    def __init__(self,platform,topic):self.platform=platform;self.topic=topic;self.target=None
    def __enter__(self):
        data=pathlib.Path(os.environ.get('CODY_DATA',pathlib.Path(__file__).resolve().parents[1]/'data'))
        pause=data/'browser-handoff.active'
        if pause.is_file():
            try:
                if json.loads(pause.read_text()).get('expires_at',0)>time.time():raise BrowserError('human_control_active')
            except FileNotFoundError:pass
            except (ValueError,OSError):
                raise BrowserError('human_control_active') from None
        from agent_reach.runtime import browser,cdp
        self.browser=browser;self.cdp=cdp
        if not browser.bound_context():raise BrowserError('browser_setup_required')
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):browser.ensure_running()
        self.target=(cdp.call('Target.createTarget',{'url':'about:blank'}) or {}).get('targetId')
        if not self.target:raise BrowserError('browser_unavailable')
        try:
            self.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
            self.call('Page.navigate',{'url':entry_url(self.platform,self.topic)})
        except Exception:
            self.cdp.call('Target.closeTarget',{'targetId':self.target});raise
        return self
    def call(self,method,params=None):
        result=self.cdp.call(method,params or {},target_id=self.target)
        if result is None:raise BrowserError('browser_unavailable')
        return result
    def evaluate(self,expression):
        result=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
        if result.get('exceptionDetails'):raise BrowserError('page_layout_unavailable')
        return result.get('result',{}).get('value')
    def snapshot(self):
        result=self.evaluate(SNAPSHOT+'('+json.dumps(self.platform)+')')
        if not isinstance(result,dict):raise BrowserError('page_layout_unavailable')
        return result
    def reject_optional_cookies(self):return self.evaluate(CONSENT) is True
    def wheel(self,viewport):
        self.browser.touch()
        self.call('Input.dispatchMouseEvent',{'type':'mouseWheel','x':int(viewport.get('width',1280)*.5),
          'y':int(viewport.get('height',900)*.55),'deltaY':int(viewport.get('height',900)*.8),'deltaX':0})
    def screenshot(self,path):
        result=self.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
        if result.get('data'):path.write_bytes(base64.b64decode(result['data']));path.chmod(0o600)
    def __exit__(self,*exc):
        if self.target:self.cdp.call('Target.closeTarget',{'targetId':self.target})

def stop_reason(platform,snapshot):
    try:p=urllib.parse.urlsplit(snapshot.get('url',''))
    except ValueError:return 'unexpected_navigation'
    if p.scheme!='https' or p.hostname not in PLATFORMS[platform]:return 'unexpected_navigation'
    if snapshot.get('status') in (403,429):return 'rate_limited' if snapshot['status']==429 else 'access_blocked'
    if snapshot.get('challenge'):return 'challenge'
    if snapshot.get('login'):return 'login_required'
    if snapshot.get('consent'):return 'consent_required'
    return None

def scan_loop(session,platform,topic,max_steps=6,max_seconds=60,dwell=2,clock=time.monotonic,sleep=time.sleep,evidence_dir=None):
    max_steps=bounded(max_steps,6,1,12);max_seconds=bounded(max_seconds,60,10,120);dwell=max(1,min(5,float(dwell)))
    started=clock();deadline=started+max_seconds;found={};steps=[];new_after_scroll=0;unchanged=0;reason='step_limit';cookie_rejected=False
    # Wait for rendered feed/ordinary consent, without requesting hidden platform APIs.
    snapshot={}
    for _ in range(8):
        snapshot=session.snapshot()
        blocked=stop_reason(platform,snapshot)
        if blocked=='unexpected_navigation' and snapshot.get('url')=='about:blank':sleep(2);continue
        if blocked in ('challenge','login_required','rate_limited','access_blocked','unexpected_navigation'):break
        if not cookie_rejected and session.reject_optional_cookies():cookie_rejected=True;sleep(2);continue
        if snapshot.get('items') or (blocked=='consent_required' and _>=3):break
        if clock()>=deadline:break
        sleep(2)
    for step in range(max_steps+1):
        blocked=stop_reason(platform,snapshot)
        if blocked:reason=blocked;break
        before=len(found);visible=[]
        for row in snapshot.get('items',[])[:30]:
            item=canonical_item(platform,row)
            if item:
                item['raw'].update(discovered_via='browser_scroll',observed_step=step)
                found.setdefault(item['url'],item);visible.append(item['url'])
        added=len(found)-before
        if step:new_after_scroll+=added
        fingerprint=hashlib.sha256(json.dumps(sorted(visible)).encode()).hexdigest()[:16]
        offset=float(snapshot.get('scroll',0))
        steps.append({'step':step,'scroll_offset':round(offset,1),'visible_items':len(visible),'new_items':added,'viewport_fingerprint':fingerprint})
        if evidence_dir is not None and step in (0,max_steps):session.screenshot(evidence_dir/(str(step).zfill(2)+'.png'))
        if step and fingerprint==steps[-2]['viewport_fingerprint'] and abs(offset-steps[-2]['scroll_offset'])<2:unchanged+=1
        else:unchanged=0
        if unchanged>=2:reason='feed_unchanged';break
        if len(found)>=40:reason='item_limit';break
        if clock()>=deadline:reason='time_limit';break
        if step==max_steps:break
        session.wheel(snapshot.get('viewport',{}));sleep(dwell)
        snapshot=session.snapshot()
    moved=any(abs(row['scroll_offset']-steps[0]['scroll_offset'])>5 or row['viewport_fingerprint']!=steps[0]['viewport_fingerprint'] for row in steps[1:]) if steps else False
    success=moved and new_after_scroll>0
    status='ok' if success else 'blocked' if reason in ('challenge','login_required','rate_limited','access_blocked','consent_required','unexpected_navigation') else 'no_new_content'
    return {'items':list(found.values())[:40], 'metrics':{'platform':platform,'topic':topic,'status':status,
      'stop_reason':reason,'scroll_steps':max(0,len(steps)-1),'viewport_changed':moved,
      'items_observed':len(found),'new_items_after_scroll':new_after_scroll,'cookie_policy':'reject_optional',
      'cookie_choice_applied':cookie_rejected,'elapsed_seconds':round(clock()-started,2),'steps':steps}}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--platform',choices=sorted(PLATFORMS),required=True);parser.add_argument('--topic',required=True)
    parser.add_argument('--steps',type=int,default=6);parser.add_argument('--seconds',type=int,default=60);parser.add_argument('--evidence',action='store_true');args=parser.parse_args()
    ident=uuid.uuid4().hex;evidence=None
    try:
        if args.evidence:
            data=pathlib.Path(os.environ.get('CODY_DATA',pathlib.Path(__file__).resolve().parents[1]/'data'))
            evidence=data/'browser-evidence'/ident;evidence.mkdir(mode=0o700,parents=True,exist_ok=True)
        with Session(args.platform,args.topic) as session:result=scan_loop(session,args.platform,args.topic,args.steps,args.seconds,evidence_dir=evidence)
        result['metrics'].update(id=ident,observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        code=error.code if isinstance(error,BrowserError) else 'browser_unavailable'
        print(json.dumps({'items':[],'metrics':{'id':ident,'platform':args.platform,'topic':args.topic,'status':'error','stop_reason':code,
          'scroll_steps':0,'viewport_changed':False,'items_observed':0,'new_items_after_scroll':0}}))

if __name__=='__main__':main()
