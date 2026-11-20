"""Small cached public TikTok reader with persistent pacing and local audio-language proof."""
import contextlib,datetime as dt,email.utils,hashlib,json,math,pathlib,re,subprocess,tempfile,threading,time,urllib.error,urllib.parse,wave,os

DB=None
DATA=None
RAW=None
LOCK=threading.Lock()
DISCOVERY_BUDGET=[2]

class Paused(ValueError):pass

def parse_profile(body,handle):
    match=re.search(r'<script[^>]*id=["\x27]__FRONTITY_CONNECT_STATE__["\x27][^>]*>(.*?)</script>',body,re.S)
    if not match:raise ValueError('TikTok liefert gerade keine öffentliche Videoliste.')
    data=json.loads(match[1]).get('source',{}).get('data',{}).get('/embed/@'+handle,{})
    user=data.get('userInfo',{})
    if data.get('isError') or user.get('privateAccount') or user.get('code') not in (None,0,200):raise ValueError('TikTok-Profil ist nicht öffentlich verfügbar.')
    if not isinstance(data.get('videoList'),list):raise ValueError('TikTok-Profilliste fehlt.')
    return data

def state():
    with DB() as c:row=c.execute("SELECT value FROM meta WHERE key='tiktok_http'").fetchone()
    return json.loads(row[0]) if row else {}

def _write(c,value):c.execute("INSERT OR REPLACE INTO meta VALUES('tiktok_http',?)",(json.dumps(value),))

def _cache(handle):
    path=DATA()/'tiktok-profile-cache'/(handle+'.json')
    try:
        if path.stat().st_size>6500000:return None
        data=json.loads(path.read_text());parse_profile(data['body'],handle)
        return data
    except (OSError,ValueError,KeyError,TypeError):return None

def retry_delay(value):
    try:return max(60,float(value))
    except (TypeError,ValueError):
        try:return max(60,email.utils.parsedate_to_datetime(value).timestamp()-time.time())
        except (TypeError,ValueError,OverflowError):return 1800

def profile(handle,max_age=3300,budget=None):
    if not re.fullmatch(r'[A-Za-z0-9_.]{2,24}',handle):raise ValueError('Ungültiger TikTok-Creator.')
    handle=handle.lower()
    with LOCK:
        cached=_cache(handle);now=time.time()
        if cached and 0<=now-cached.get('fetched_at',0)<=max_age:return cached['body']
        if budget is not None and budget[0]<=0:raise Paused('TikTok-Prüflimit für neue Profile erreicht.')
        # A SQLite lease coordinates the collector, discovery and explicit verification processes.
        with DB() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT value FROM meta WHERE key='tiktok_http'").fetchone();current=json.loads(row[0]) if row else {}
            if current.get('cooldown_until',0)>now:raise Paused('TikTok begrenzt Abrufe; die Pause wird eingehalten.')
            if current.get('lease_until',0)>now:raise Paused('Ein TikTok-Abruf läuft bereits.')
            delay=max(0,current.get('next_allowed_at',0)-now)
            if delay>15:raise Paused('TikTok wartet vor dem nächsten Abruf.')
            current['lease_until']=now+delay+40;_write(c,current)
        if budget is not None:budget[0]-=1
        if delay:time.sleep(delay)
        try:
            body=RAW('https://www.tiktok.com/embed/@'+handle)
            parse_profile(body,handle)
            folder=DATA()/'tiktok-profile-cache';folder.mkdir(mode=0o700,exist_ok=True)
            path=folder/(handle+'.json');temporary=folder/(handle+'.tmp')
            temporary.write_text(json.dumps({'fetched_at':time.time(),'body':body}));temporary.chmod(0o600);temporary.replace(path)
            with DB() as c:_write(c,{'lease_until':0,'next_allowed_at':time.time()+10,'cooldown_until':0,'last_success_at':time.time()})
            return body
        except Exception as error:
            with DB() as c:
                current['lease_until']=0;current['next_allowed_at']=time.time()+10
                if isinstance(error,urllib.error.HTTPError) and error.code in (403,429):
                    current['cooldown_until']=time.time()+retry_delay(error.headers.get('Retry-After'))
                    current['http_status']=error.code
                _write(c,current)
            if isinstance(error,urllib.error.HTTPError) and error.code in (403,429):raise Paused('TikTok begrenzt Abrufe; die Pause wird eingehalten.') from None
            raise ValueError('Öffentliches TikTok-Profil derzeit nicht abrufbar.') from None

def discover_items(indexed,eligible):
    result=[];handles=set();failures=[]
    for item in indexed[:6]:
        match=re.fullmatch(r'https://(?:www\.)?tiktok.com/@([\w.]{2,24})(?:/video/\d{15,25})?/?(?:[?#].*)?',str(item.get('url') or ''))
        if not match:continue
        handle=match[1].lower()
        if handle in handles or not eligible(handle):continue
        handles.add(handle)
        try:data=parse_profile(profile(handle,max_age=21600,budget=DISCOVERY_BUDGET),handle)
        except ValueError as e:failures.append(str(e));continue
        videos=sorted(data['videoList'],key=lambda v:str(v.get('id','')),reverse=True)
        for video in videos[:4]:
            ident=str(video.get('id',''))
            if not re.fullmatch(r'\d{15,25}',ident) or video.get('authorUniqueId','').lower()!=handle or video.get('privateItem'):continue
            age=time.time()-(int(ident)>>32)
            if not 0<=age<=30*86400:continue
            try:proof=detect_language(video)
            except ValueError as e:failures.append(str(e));break
            if proof['language']!='de' or proof['confidence']<.95 or not proof['speech_heard']:continue
            result.append({'url':'https://www.tiktok.com/@'+handle+'/video/'+ident,'text':video.get('desc',''),
                           'author':data.get('userInfo',{}).get('nickname') or handle,'raw':{'language':'de'}})
    if not result and failures:raise Paused(failures[0])
    return result

def _ffmpeg():
    import shutil
    configured=os.environ.get('CODY_FFMPEG') or shutil.which('ffmpeg')
    if configured:return configured
    python=DATA()/'reach/venv/bin/python'
    command=[str(python),'-c','from agent_reach.transcribe import _bin; print(_bin("ffmpeg"))']
    env={**os.environ,'HOME':str(DATA()/'reach'),'USERPROFILE':str(DATA()/'reach')}
    p=subprocess.run(command,capture_output=True,text=True,timeout=15,env=env)
    path=pathlib.Path(p.stdout.strip())
    if p.returncode or not path.is_absolute() or not path.is_file():raise ValueError('Lokales Audiowerkzeug fehlt.')
    return str(path)

def parse_language_result(output,diagnostic):
    match=re.search(r'auto-detected language:\s*([a-z]{2,3})\s*\(p\s*=\s*([\d.]+)\)',diagnostic)
    if not match:raise ValueError('Lokaler Sprachnachweis fehlt.')
    confidence=float(match[2]);language=match[1]
    if not math.isfinite(confidence) or not 0<=confidence<=1:raise ValueError('Ungültiger Sprachnachweis.')
    text=' '.join(row.get('text','') for row in output.get('transcription',[]))
    has_speech=sum(ch.isalpha() for ch in text)>=15 and len(re.findall(r'\w+',text))>=3
    return {'language':language,'confidence':confidence,'speech_heard':has_speech}

def detect_language(video):
    ident=str(video['id'])
    folder=DATA()/'tiktok-language-results';folder.mkdir(mode=0o700,exist_ok=True)
    cache=folder/(ident+'.json')
    if cache.is_file():
        try:
            result=json.loads(cache.read_text())
            if result.get('method')=='whisper.cpp-tiny-q5_1':return result
        except ValueError:pass
    root=DATA()/'tiktok-language';binary=pathlib.Path(os.environ.get('CODY_WHISPER_BIN',str(root/'whisper-cli')));model=pathlib.Path(os.environ.get('CODY_WHISPER_MODEL',str(root/'ggml-tiny-q5_1.bin')))
    if not binary.is_file() or not model.is_file():raise ValueError('Lokale Sprachprüfung ist noch nicht eingerichtet.')
    url=video.get('playAddr','')
    if not isinstance(url,str):raise ValueError('Öffentliche TikTok-Audiospur fehlt.')
    parsed=urllib.parse.urlsplit(url);host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.port or not host.endswith(('.tiktok.com','.tiktokcdn.com','.tiktokcdn-eu.com','.byteoversea.com')):
        raise ValueError('Öffentliche TikTok-Audiospur ist nicht unterstützt.')
    with tempfile.TemporaryDirectory(prefix='cody-tiktok-language-') as directory:
        directory=pathlib.Path(directory);audio=directory/'sample.wav';out=directory/'result'
        p=subprocess.run([_ffmpeg(),'-hide_banner','-loglevel','error','-nostdin','-threads','1','-rw_timeout','15000000',
          '-i',url,'-t','12','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-fs','450000',str(audio)],capture_output=True,timeout=45)
        if p.returncode or not audio.is_file() or not 16000<audio.stat().st_size<=450000:raise ValueError('TikTok-Hörprobe derzeit nicht verfügbar.')
        with wave.open(str(audio),'rb') as wav:seconds=wav.getnframes()/wav.getframerate()
        if not 3<=seconds<=12.5:raise ValueError('TikTok-Hörprobe ist zu kurz.')
        p=subprocess.run(['/usr/bin/nice','-n','10',str(binary),'-m',str(model),'-f',str(audio),'-t','2','-l','auto',
                          '-oj','-of',str(out),'-nt','-ng'],capture_output=True,text=True,timeout=120)
        output=out.with_suffix('.json')
        if p.returncode or not output.is_file() or output.stat().st_size>1000000:raise ValueError('Lokale Sprachprüfung derzeit nicht verfügbar.')
        result=parse_language_result(json.loads(output.read_text()),p.stderr)
        result.update(method='whisper.cpp-tiny-q5_1',sample_seconds=round(seconds,2),checked_at=time.time())
    temporary=cache.with_suffix('.tmp');temporary.write_text(json.dumps(result));temporary.chmod(0o600);temporary.replace(cache)
    return result

def hydrate(item,budget=None):
    handle=item['handle'];ident=item['url'].rsplit('/',1)[-1]
    data=parse_profile(profile(handle,max_age=21600,budget=budget),handle)
    video=next((v for v in data['videoList'] if str(v.get('id'))==ident and v.get('authorUniqueId','').lower()==handle and not v.get('privateItem')),None)
    if not video:raise ValueError('TikTok-Video nicht mehr in der geprüften öffentlichen Liste.')
    proof=detect_language(video)
    ready=proof['language']=='de' and proof['confidence']>=.95 and proof['speech_heard']
    return {'external_id':ident,'kind':'video','format':'short','title':str(video.get('desc') or item['title'])[:1000],
            'url':'https://www.tiktok.com/@'+handle+'/video/'+ident,'thumbnail':str(video.get('coverUrl') or ''),
            'text':'','media':[],'language':proof['language'],
            'language_basis':'Lokale Hörprobe bis 12 s, whisper.cpp tiny-q5_1',
            **({} if ready else {'status':'language_unconfirmed','message':'Keine ausreichend sichere deutsche Sprache in der Hörprobe.'})}
