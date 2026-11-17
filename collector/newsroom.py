"""RSS, grounded video news and bounded discovery. No browser login or posting."""
from __future__ import annotations
import contextlib, datetime as dt, email.utils, hashlib, html, http.client, ipaddress
import json, os, pathlib, re, socket, ssl, subprocess, threading, time, urllib.parse, secrets, importlib.util, sys, shutil
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

DB = None
DATA = None
UTC = None
PUBLIC = None
X_LOCK = None
PARSE_X = None
PARSE_TAB = None
TIKTOK_RAW = None
_tiktok_spec=importlib.util.spec_from_file_location('cody_tiktok_discovery',pathlib.Path(__file__).with_name('tiktok_discovery.py'))
tiktok=importlib.util.module_from_spec(_tiktok_spec);_tiktok_spec.loader.exec_module(tiktok)
LOCK = threading.Lock()
BUSY = False
DEFAULTS = {'enabled': False, 'topics': ['KI', 'Automatisierung', 'praktische KI-Werkzeuge'],
            'exclude': [], 'platforms': ['youtube', 'x', 'tiktok'], 'runs_per_day': 2, 'max_suggestions': 3}

def initialize(c):
    tiktok.DB=DB;tiktok.DATA=DATA;tiktok.RAW=TIKTOK_RAW;tiktok.DISCOVERY_BUDGET=[2]
    columns = {r['name'] for r in c.execute('PRAGMA table_info(sources)')}
    if 'delivery' not in columns:
        c.execute("ALTER TABLE sources ADD COLUMN delivery TEXT NOT NULL DEFAULT 'videos'")
        c.execute("UPDATE sources SET delivery='news' WHERE platform='x'")
    columns = {r['name'] for r in c.execute('PRAGMA table_info(posts)')}
    for name, definition in {'kind': "TEXT NOT NULL DEFAULT 'x'", 'title': "TEXT NOT NULL DEFAULT ''",
                             'date_known': 'INTEGER NOT NULL DEFAULT 1'}.items():
        if name not in columns:c.execute('ALTER TABLE posts ADD COLUMN '+name+' '+definition)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS summaries (
      video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'pending', transcript TEXT NOT NULL DEFAULT '',
      text_hash TEXT NOT NULL DEFAULT '', text_de TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
      next_at REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS discovery_runs (
      id INTEGER PRIMARY KEY, slot TEXT UNIQUE NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
      status TEXT NOT NULL DEFAULT 'collecting', input_json TEXT NOT NULL DEFAULT '{}',
      input_hash TEXT NOT NULL DEFAULT '', next_at REAL NOT NULL DEFAULT 0,
      message TEXT NOT NULL DEFAULT '', platforms_json TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS suggestions (
      id TEXT PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES discovery_runs(id),
      platform TEXT NOT NULL, handle TEXT NOT NULL, creator TEXT NOT NULL, profile_url TEXT NOT NULL,
      url TEXT NOT NULL, title TEXT NOT NULL, evidence TEXT NOT NULL, reason TEXT NOT NULL,
      published_at TEXT, topic TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL,
      UNIQUE(platform,handle));
    CREATE TABLE IF NOT EXISTS muted_creators (
      platform TEXT NOT NULL, handle TEXT NOT NULL, PRIMARY KEY(platform,handle));
    CREATE TABLE IF NOT EXISTS discovery_content (
      suggestion_id TEXT PRIMARY KEY REFERENCES suggestions(id) ON DELETE CASCADE,
      platform TEXT NOT NULL, external_id TEXT NOT NULL, kind TEXT NOT NULL, format TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, thumbnail TEXT NOT NULL DEFAULT '',
      text TEXT NOT NULL DEFAULT '', text_de TEXT NOT NULL DEFAULT '', text_hash TEXT NOT NULL DEFAULT '',
      translation_status TEXT NOT NULL DEFAULT 'pending', translation_next_at REAL NOT NULL DEFAULT 0,
      media_json TEXT NOT NULL DEFAULT '[]', language TEXT NOT NULL DEFAULT '', language_basis TEXT NOT NULL DEFAULT '',
      seen INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
      message TEXT NOT NULL DEFAULT '', next_at REAL NOT NULL DEFAULT 0, updated_at TEXT);
    ''')
    columns={r['name'] for r in c.execute('PRAGMA table_info(summaries)')}
    for name,definition in {'basis':"TEXT NOT NULL DEFAULT 'Öffentliche YouTube-Untertitel'",'speech_lease':"TEXT NOT NULL DEFAULT ''"}.items():
        if name not in columns:c.execute('ALTER TABLE summaries ADD COLUMN '+name+' '+definition)
    muted_columns={r['name'] for r in c.execute('PRAGMA table_info(muted_creators)')}
    for name,definition in {'title':"TEXT NOT NULL DEFAULT ''",'resume_json':"TEXT NOT NULL DEFAULT '[]'"}.items():
        if name not in muted_columns:c.execute('ALTER TABLE muted_creators ADD COLUMN '+name+' '+definition)
    c.execute("UPDATE summaries SET status='awaiting_speech',next_at=0,message='Spracherkennung ist nicht konfiguriert.' WHERE status='unavailable' AND message LIKE '%RATE_LIMITED%'")
    c.execute("INSERT OR IGNORE INTO meta VALUES('discovery_settings',?)", (json.dumps(DEFAULTS, ensure_ascii=False),))

class Plain(HTMLParser):
    def __init__(self):super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        elif tag in ('p','br','div','li'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

def plain(value):
    p=Plain();p.feed(str(value or '')[:200000])
    return re.sub(r'\n\s*\n+', '\n\n', ''.join(p.parts)).strip()[:30000]

def public_url(value):
    p=urllib.parse.urlsplit(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port or p.fragment or len(value)>2000:
        raise ValueError('Bitte eine öffentliche HTTPS-Feed-Adresse ohne Zugangsdaten verwenden.')
    host=p.hostname.encode('idna').decode('ascii')
    if host=='localhost' or host.endswith(('.local','.internal','.localhost','.ts.net')):
        raise ValueError('Interne Adressen sind keine öffentlichen Feeds.')
    addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('Interne Adressen sind keine öffentlichen Feeds.')
    return p,host,addresses

def fetch_feed(url):
    """Validate and pin DNS per redirect; TLS still authenticates the original hostname."""
    for hop in range(5):
        p,host,addresses=public_url(url)
        class Pinned(http.client.HTTPSConnection):
            def connect(self):
                self.sock=self._context.wrap_socket(socket.create_connection((addresses[0],443),self.timeout), server_hostname=host)
        connection=Pinned(host,timeout=25,context=ssl.create_default_context())
        try:
            connection.request('GET',urllib.parse.urlunsplit(('', '', p.path or '/', p.query, '')),
                               headers={'User-Agent':'KISocialMedia/0.4 (+private RSS reader)','Accept':'application/rss+xml,application/atom+xml,application/xml,text/xml','Accept-Encoding':'identity'})
            r=connection.getresponse()
            if r.status in (301,302,303,307,308):
                url=urllib.parse.urljoin(url,r.getheader('Location',''));continue
            if r.status!=200:raise ValueError('Der Feed antwortet mit HTTP '+str(r.status)+'.')
            data=r.read(2000001)
            if len(data)>2000000:raise ValueError('Der Feed ist zu groß (maximal 2 MB).')
            if b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Feed mit XML-Entitäten oder UTF-16/32 wird nicht verarbeitet.')
            return data,url
        finally:connection.close()
    raise ValueError('Zu viele Feed-Weiterleitungen.')

def canonical(url):
    try:
        p=urllib.parse.urlsplit(url)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.port:return ''
        query=[(k,v) for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True)
               if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')]
        return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',urllib.parse.urlencode(query),''))
    except ValueError:return ''

def parsed_date(value):
    try:
        try:d=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:d=email.utils.parsedate_to_datetime(value)
        if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat()
    except (TypeError,ValueError,OverflowError,AttributeError):return None

def parse_feed(body,url):
    if b'\x00' in body or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():raise ValueError('XML-Entitäten oder UTF-16/32 nicht unterstützt.')
    root=ET.fromstring(body)
    local=lambda tag:tag.rsplit('}',1)[-1]
    atom=local(root.tag)=='feed'
    channel=root if atom else root.find('channel')
    if channel is None:raise ValueError('Kein RSS- oder Atom-Feed gefunden.')
    def child(node,*names):
        return next((e for e in node if local(e.tag) in names),None)
    def value(node,*names):
        e=child(node,*names)
        return ''.join(e.itertext()) if e is not None else ''
    title=plain(value(channel,'title'))[:200] or urllib.parse.urlsplit(url).hostname
    entries=[e for e in channel if local(e.tag) in ('entry','item')]
    result={}
    for item in entries[:60]:
        links=[e for e in item if local(e.tag)=='link']
        link=next((e.get('href','') for e in links if e.get('rel','alternate')=='alternate'), '') if atom else value(item,'link')
        link=canonical(urllib.parse.urljoin(url,link.strip())) if link else ''
        ident=value(item,'guid','id').strip() or link
        if not ident:continue
        entry_title=plain(value(item,'title'))[:1000]
        content=plain(value(item,'encoded','content','description','summary'))
        text=entry_title+('\n\n'+content if content and content!=entry_title else '')
        if not text.strip():continue
        published=parsed_date(value(item,'published','pubDate','date','updated'))
        result[ident]={'external_id':hashlib.sha256(ident.encode()).hexdigest(), 'author':title,'title':entry_title,
                      'text':text[:30000],'url':link or url,'published_at':published,'media':[]}
    return list(result.values()),{'title':title}

def collect_rss(source):
    body,url=fetch_feed(source['handle']);rows,meta=parse_feed(body,url)
    return rows,meta,[]

def save_rss(c,source,rows,now):
    for v in rows:
        digest=hashlib.sha256(v['text'].encode()).hexdigest()
        c.execute('''INSERT INTO posts(id,source_id,external_id,author,title,text,url,published_at,
          discovered_at,text_hash,kind,date_known) VALUES(?,?,?,?,?,?,?,?,?,?,'rss',?)
          ON CONFLICT(id) DO UPDATE SET title=excluded.title,text=excluded.text,url=excluded.url,
          text_de=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.text_de ELSE '' END,
          translation_status=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.translation_status ELSE 'pending' END,
          translation_next_at=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.translation_next_at ELSE 0 END,
          text_hash=excluded.text_hash,published_at=CASE WHEN excluded.date_known=1 THEN excluded.published_at ELSE posts.published_at END,
          date_known=excluded.date_known''',('rss:'+str(source['id'])+':'+v['external_id'],source['id'],v['external_id'],v['author'],
            v['title'],v['text'],v['url'],v.get('published_at') or now,now,digest,int(bool(v.get('published_at')))))

def settings():
    with DB() as c:return json.loads(c.execute("SELECT value FROM meta WHERE key='discovery_settings'").fetchone()[0])

def set_settings(body):
    allowed=set(DEFAULTS)
    if set(body)-allowed:raise ValueError('Unbekannte Entdecker-Einstellung.')
    data={**settings(),**body}
    for key in ('topics','exclude'):
        if not isinstance(data[key],list) or len(data[key])>12 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in data[key]):
            raise ValueError('Bitte bis zu zwölf kurze Themen oder Ausschlüsse angeben.')
        data[key]=list(dict.fromkeys(x.strip() for x in data[key]))
    if not data['topics']:raise ValueError('Mindestens ein Thema ist nötig.')
    if not isinstance(data['platforms'],list) or not data['platforms'] or set(data['platforms'])-{'youtube','x','tiktok'}:raise ValueError('Ungültige Plattformen.')
    if type(data['runs_per_day']) is not int or data['runs_per_day'] not in (1,2):raise ValueError('Ein oder zwei Läufe täglich wählen.')
    if type(data['max_suggestions']) is not int or not 1<=data['max_suggestions']<=3:raise ValueError('Ein bis drei Vorschläge wählen.')
    if type(data['enabled']) is not bool:raise ValueError('Aktiv muss wahr oder falsch sein.')
    with DB() as c:c.execute("UPDATE meta SET value=? WHERE key='discovery_settings'",(json.dumps(data,ensure_ascii=False),))
    return data

def reach(channel,action,target,**options):
    home=DATA()/'reach';binary=pathlib.Path(os.environ.get('CODY_REACH_BIN',shutil.which('agent-reach') or str(home/'venv/bin/agent-reach')))
    args=[str(binary),channel,action,target]
    for key,value in options.items():args+=['--'+key.replace('_','-'),str(value)]
    args+=['--timeout','70']
    env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'PYTHONUNBUFFERED':'1'}
    try:
        with X_LOCK if channel=='twitter' else contextlib.nullcontext():
            p=subprocess.run(args,capture_output=True,text=True,timeout=100,env=env)
        if len(p.stdout)>3000000:raise ValueError()
        payload=json.loads(p.stdout)
    except Exception:raise ValueError('Der '+channel+'-Abruf ist derzeit nicht verfügbar.') from None
    if p.returncode or not isinstance(payload,dict) or not payload.get('ok'):
        code=payload.get('error',{}).get('code','') if isinstance(payload,dict) else ''
        raise ValueError('Der '+channel+'-Abruf ist derzeit nicht verfügbar'+(' ('+code+')' if re.fullmatch('[A-Z_]{1,40}',code) else '')+'.')
    items=payload.get('items')
    if not isinstance(items,list):raise ValueError('Ungültige Plattformantwort.')
    return items

def queue_summary(video_id):
    with DB() as c:
        row=c.execute('SELECT id FROM videos WHERE id=?',(video_id,)).fetchone()
        if not row:raise ValueError('Video nicht gefunden.')
        c.execute('INSERT OR IGNORE INTO summaries(video_id) VALUES(?)',(video_id,))

def prepare_summaries():
    with DB() as c:
        c.execute('''INSERT OR IGNORE INTO summaries(video_id)
          SELECT v.id FROM videos v JOIN sources s ON s.id=v.source_id
          WHERE s.enabled=1 AND s.delivery IN ('news','both') AND v.feed_eligible=1 AND v.seen=0''')
        rows=[dict(r) for r in c.execute('''SELECT j.*,v.external_id,v.platform FROM summaries j
          JOIN videos v ON v.id=j.video_id JOIN sources s ON s.id=v.source_id
          WHERE s.enabled=1 AND j.status IN ('pending','unavailable') AND j.next_at<=?
          ORDER BY v.published_at DESC LIMIT 2''',(time.time(),))]
    for row in rows:
        try:
            if row['platform']!='youtube':raise ValueError('Für TikTok ist noch kein vollständiges Transkript verfügbar.')
            items=reach('youtube','subtitle',row['external_id'],lang='de,en,en-orig')
            text='\n'.join(i.get('text','') for i in items if isinstance(i,dict))
            if len(text.strip())<100:raise ValueError('Kein ausreichend langes Transkript verfügbar.')
            if len(text)>120000:raise ValueError('Das Transkript ist für die vollständige Zusammenfassung zu lang.')
            with DB() as c:c.execute("UPDATE summaries SET transcript=?,text_hash=?,status='queued',message='',next_at=0,updated_at=? WHERE video_id=?",
              (text,hashlib.sha256(text.encode()).hexdigest(),UTC(),row['video_id']))
        except Exception as e:
            fallback=row['platform']=='youtube' and 'PLATFORM_BLOCKED' not in str(e)
            message=('Untertitel nicht verfügbar. '+('Whisper-Audioabruf wartet.' if speech_status().get('available') else 'Spracherkennung ist nicht konfiguriert.')) if fallback else str(e)[:250]
            with DB() as c:c.execute("UPDATE summaries SET status=?,message=?,attempts=attempts+1,next_at=?,updated_at=? WHERE video_id=?",
              ('awaiting_speech' if fallback else 'unavailable',message,0 if fallback else time.time()+21600,UTC(),row['video_id']))

def speech_status():
    with DB() as c:row=c.execute("SELECT value FROM meta WHERE key='speech_status'").fetchone()
    return json.loads(row[0]) if row else {'available':False,'message':'Spracherkennung ist nicht konfiguriert.'}

def set_speech_status(body):
    value={'available':body.get('available') is True,'provider':body.get('provider') if body.get('provider') in ('openai','groq','local','compatible') else '', 'checked_at':UTC()}
    with DB() as c:c.execute("INSERT OR REPLACE INTO meta VALUES('speech_status',?)",(json.dumps(value),))

def claim_speech():
    with DB() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('''SELECT j.video_id,v.url FROM summaries j JOIN videos v ON v.id=j.video_id
          JOIN sources s ON s.id=v.source_id WHERE s.enabled=1 AND v.platform='youtube'
          AND j.status IN ('awaiting_speech','speech_working') AND j.next_at<=?
          ORDER BY v.published_at DESC LIMIT 1''',(time.time(),)).fetchone()
        if not row:return []
        lease=secrets.token_hex(16)
        c.execute("UPDATE summaries SET status='speech_working',speech_lease=?,next_at=?,message='Audiospur wird transkribiert.' WHERE video_id=?",(lease,time.time()+7200,row['video_id']))
        return [{'id':row['video_id'],'url':row['url'],'lease':lease}]

def complete_speech(body):
    ident=str(body.get('id',''));lease=str(body.get('lease',''));text=body.get('text','')
    with DB() as c:
        row=c.execute("SELECT 1 FROM summaries WHERE video_id=? AND speech_lease=? AND status='speech_working'",(ident,lease)).fetchone()
        if not row:return 0
        if body.get('error'):
            c.execute("UPDATE summaries SET status='awaiting_speech',next_at=?,message='Whisper-Audioabruf fehlgeschlagen; späterer Versuch.',updated_at=? WHERE video_id=?",(time.time()+21600,UTC(),ident))
            return 0
        if not isinstance(text,str) or not 100<=len(text)<=120000:raise ValueError('Ungültiges Whisper-Transkript.')
        provider=body.get('provider')
        if provider not in ('openai','groq','local','compatible'):raise ValueError('Ungültiger Whisper-Anbieter.')
        c.execute("UPDATE summaries SET status='queued',transcript=?,text_hash=?,next_at=0,message='',basis=?,updated_at=? WHERE video_id=?",
          (text,hashlib.sha256(text.encode()).hexdigest(),('Audiospur, konfigurierte Spracherkennung ('+provider+')'),UTC(),ident))
        return 1

def candidate(platform,item,topic):
    if not isinstance(item,dict):return None
    raw=item.get('raw') if isinstance(item.get('raw'),dict) else {}
    url=str(item.get('url') or '')
    if platform=='x':
        m=re.fullmatch(r'https://(?:www\.)?(?:x.com|twitter.com)/([\w]{1,15})/status/(\d{15,25})(?:[?#].*)?',url)
        if not m:return None
        handle=m[1].lower()
        if handle=='i':
            # OpenCLI search emits /i/status URLs plus the actual username in raw.author.
            handle=str(raw.get('screen_name') or raw.get('username') or raw.get('author') or '').lstrip('@').lower()
        if not re.fullmatch(r'[a-z0-9_]{1,15}',handle) or handle in {'i','home','search','explore','intent','share','settings','notifications','messages'}:return None
        profile='https://x.com/'+handle
        url=profile+'/status/'+m[2]
        date=dt.datetime.fromtimestamp(((int(m[2])>>22)+1288834974657)/1000,dt.timezone.utc).isoformat()
    elif platform=='youtube':
        if not re.fullmatch(r'https://www.youtube.com/watch\?v=[\w-]{11}',url):return None
        handle=raw.get('channel_id','')
        if not re.fullmatch(r'UC[\w-]{22}',handle):return None
        profile='https://www.youtube.com/channel/'+handle;date=parsed_date(item.get('published_at'))
    else:
        m=re.fullmatch(r'https://(?:www\.)?tiktok.com/@([\w.]{2,24})/video/(\d{15,25})(?:[?#].*)?',url)
        if not m:return None
        handle=m[1].lower();profile='https://www.tiktok.com/@'+handle
        date=dt.datetime.fromtimestamp(int(m[2])>>32,dt.timezone.utc).isoformat()
    if not date:return None
    age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(date)).total_seconds()
    if not 0<=age<=30*86400:return None
    evidence=plain(item.get('text') or item.get('title') or '')[:2000]
    if len(evidence)<30:return None
    return {'id':hashlib.sha256(url.encode()).hexdigest()[:24], 'platform':platform,'handle':handle,
      'creator':str(item.get('author') or handle)[:200], 'profile_url':profile,'url':canonical(url),
      'title':plain(item.get('title') or evidence[:140])[:300], 'evidence':evidence,
      'published_at':date,'topic':topic,'language':str(raw.get('language') or ''),
      'basis':'Beitragstext' if platform=='x' else 'Titel und Beschreibung'}

def recent_youtube_search(query):
    home=DATA()/'reach';env={**os.environ,'HOME':str(home),'USERPROFILE':str(home)}
    url='https://www.youtube.com/results?'+urllib.parse.urlencode({'search_query':query+' deutsch','sp':'CAISAhAB'})
    args=[sys.executable,'-m','yt_dlp','--ignore-config','--flat-playlist','--skip-download',
          '--dump-json','--playlist-end','8','--no-warnings','--socket-timeout','25','--retries','0','--',url]
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=100,env=env)
        if p.returncode or len(p.stdout)>4000000:raise ValueError()
        return [json.loads(line) for line in p.stdout.splitlines() if line.strip()][:8]
    except Exception:raise ValueError('Die aktuelle YouTube-Suche ist derzeit nicht verfügbar.') from None

def collect_discovery(platform,topic):
    query={'KI':'Künstliche Intelligenz AI Tools','Automatisierung':'KI Automatisierung Agenten',
           'praktische KI-Werkzeuge':'KI Tools Claude Codex'}.get(topic,topic)
    if platform=='x':
        query={'KI':'(KI OR AI) (Tools OR Claude OR Codex OR Agenten)',
          'Automatisierung':'(KI OR AI) (Automatisierung OR automation)',
          'praktische KI-Werkzeuge':'(Claude OR Codex OR ChatGPT) (Tool OR Workflow OR Tutorial)'}.get(topic,topic)
        return reach('twitter','search',query+' -filter:retweets -filter:replies',limit=8)
    if platform=='youtube':
        rows=recent_youtube_search(query)
        # Recent ordering prevents old popular tutorials from using every candidate slot.
        verified=[];errors=[]
        for item in rows[:8]:
            url=str(item.get('url') or '')
            if not re.fullmatch(r'https://www.youtube.com/watch\?v=[\w-]{11}',url):continue
            try:
                meta=video_metadata(url)
                if meta['language']!='de':continue
                entry={'url':url,'title':meta['title'],'text':meta['description'],
                  'author':meta['creator'],'published_at':meta['published_at'],
                  'raw':{'channel_id':meta['channel_id'],'language':meta['language']}}
                parsed=candidate('youtube',entry,topic)
                if not parsed:continue
                with DB() as c:
                    if not allowed_candidate(c,parsed,settings()):continue
                verified.append(entry)
                if len(verified)>=3:break
            except ValueError as e:errors.append(str(e))
        if errors and not verified:raise ValueError(errors[0])
        return verified
    # TikTok has no Agent Reach channel. Search the public index, then confirm against the real profile.
    indexed=reach('web','search','site:tiktok.com '+query+' deutsch',limit=6)
    def eligible(handle):
        with DB() as c:
            return not c.execute("SELECT 1 FROM sources WHERE platform='tiktok' AND lower(handle)=?",(handle,)).fetchone() and not c.execute(
              "SELECT 1 FROM muted_creators WHERE platform='tiktok' AND handle=?",(handle,)).fetchone() and not c.execute(
              "SELECT 1 FROM suggestions WHERE platform='tiktok' AND handle=?",(handle,)).fetchone()
    return tiktok.discover_items(indexed,eligible)

def allowed_candidate(c,item,config):
    if any(x.casefold() in (item['title']+' '+item['evidence']+' '+item['creator']).casefold() for x in config['exclude']):return False
    if c.execute('SELECT 1 FROM muted_creators WHERE platform=? AND handle=?',(item['platform'],item['handle'])).fetchone():return False
    if c.execute('SELECT 1 FROM suggestions WHERE platform=? AND handle=?',(item['platform'],item['handle'])).fetchone():return False
    if c.execute('''SELECT 1 FROM sources WHERE platform=? AND (lower(handle)=lower(?) OR channel_id=?)''',
                 (item['platform'],item['handle'],item['handle'])).fetchone():return False
    return True

def discover(force=False,platforms=None):
    config=settings()
    if not config['enabled']:return
    if platforms is not None:
        config['platforms']=[p for p in config['platforms'] if p in platforms]
        if not config['platforms']:return
    if 'tiktok' in config['platforms']:tiktok.DISCOVERY_BUDGET=[2]
    # UTC slots avoid a timezone-data dependency on Windows. Stable unique slot also survives restarts/DST.
    now=dt.datetime.now(dt.timezone.utc)
    slot=('manual:'+str(int(time.time()//600))+(':'+','.join(config['platforms']) if platforms is not None else '')) if force else now.date().isoformat()+':'+str(now.hour//(24//config['runs_per_day']))
    if force:slot+=':'+hashlib.sha256(pathlib.Path(__file__).read_bytes()+pathlib.Path(tiktok.__file__).read_bytes()).hexdigest()[:12]
    with DB() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE discovery_runs SET status='interrupted',finished_at=?,message='Abruf unterbrochen; nächster regulärer Lauf folgt.' WHERE status='collecting' AND next_at<=?",(UTC(),time.time()))
        if c.execute('SELECT 1 FROM discovery_runs WHERE slot=?',(slot,)).fetchone():return
        ident=c.execute('INSERT INTO discovery_runs(slot,started_at,next_at) VALUES(?,?,?)',(slot,UTC(),time.time()+900)).lastrowid
    candidates={};states={}
    # Rotate topics between slots; two small queries/platform, not a continuous feed crawl.
    offset=int(now.timestamp()//43200)%len(config['topics'])
    topics=(config['topics']*2)[offset:offset+min(2,len(config['topics']))]
    for platform in config['platforms']:
        count=0;errors=[]
        for topic in topics:
            try:
                rows=collect_discovery(platform,topic)
                for row in rows:
                    item=candidate(platform,row,topic)
                    if item:
                        with DB() as c:allowed=allowed_candidate(c,item,config)
                        if allowed:candidates[item['id']]=item;count+=1
            except Exception as e:errors.append(str(e)[:250]);break
        states[platform]={'status':'error' if errors else 'ok','candidates':count,'message':' '.join(errors)}
        if platform=='tiktok' and tiktok.state().get('cooldown_until',0)>time.time():
            states[platform].update(status='partial' if count else 'error',message='TikTok-Pause aktiv; vorhandener Cache bleibt nutzbar.')
    # Interleave platforms before the cap, so X cannot fill every model candidate slot.
    ordered=[];groups={p:[v for v in candidates.values() if v['platform']==p] for p in config['platforms']}
    while any(groups.values()) and len(ordered)<24:
        for group in groups.values():
            if group and len(ordered)<24:ordered.append(group.pop(0))
    payload={'candidates':ordered,'topics':config['topics'],'exclude':config['exclude'],'limit':config['max_suggestions']}
    encoded=json.dumps(payload,ensure_ascii=False);digest=hashlib.sha256(encoded.encode()).hexdigest()
    with DB() as c:c.execute('''UPDATE discovery_runs SET status=?,input_json=?,input_hash=?,platforms_json=?,
      finished_at=?,message=?,next_at=0 WHERE id=?''',('queued' if ordered else 'empty',encoded,digest,json.dumps(states),
      None if ordered else UTC(),'' if ordered else 'Keine ausreichend aktuellen, geprüften neuen Creator gefunden.',ident))

def repair_initial_x_identity():
    """Re-evaluate the first public acceptance batch without repeating upstream requests."""
    with DB() as c:
        for row in c.execute('SELECT id,input_json FROM discovery_runs').fetchall():
            data=json.loads(row['input_json']);changed=False
            for item in data.get('candidates',[]):
                if item['platform']!='x' or item['handle']!='i':continue
                # These original rows came from the proven OpenCLI raw.author -> item.author mapping.
                handle=item['creator'].lower()
                if not re.fullmatch(r'[a-z0-9_]{1,15}',handle) or handle=='i':continue
                item['handle']=handle;item['profile_url']='https://x.com/'+handle
                item['url']=item['profile_url']+'/status/'+item['url'].rsplit('/',1)[-1];changed=True
            if changed:
                encoded=json.dumps(data,ensure_ascii=False)
                c.execute("DELETE FROM suggestions WHERE run_id=? AND platform='x' AND handle='i' AND state='new'",(row['id'],))
                c.execute("UPDATE discovery_runs SET status='queued',input_json=?,input_hash=?,next_at=0,finished_at=NULL,message='' WHERE id=?",
                  (encoded,hashlib.sha256(encoded.encode()).hexdigest(),row['id']))

def tick():
    if os.environ.get('AI_ENABLED','false').lower()!='true':return
    global BUSY
    with LOCK:
        if BUSY:return
        BUSY=True
    def run():
        global BUSY
        try:prepare_summaries();hydrate_suggestions();discover()
        finally:
            with LOCK:BUSY=False
    threading.Thread(target=run,daemon=True,name='newsroom').start()

def claim_jobs():
    with DB() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM summaries WHERE status IN ('queued','working') AND next_at<=? LIMIT 1",(time.time(),)).fetchone()
        if row:
            c.execute("UPDATE summaries SET status='working',next_at=? WHERE video_id=?",(time.time()+300,row['video_id']))
            return [{'id':row['video_id'],'kind':'summary','text':row['transcript'],'text_hash':row['text_hash']}]
        row=c.execute("SELECT * FROM discovery_runs WHERE status IN ('queued','working') AND next_at<=? ORDER BY id DESC LIMIT 1",(time.time(),)).fetchone()
        if row:
            c.execute("UPDATE discovery_runs SET status='working',next_at=? WHERE id=?",(time.time()+300,row['id']))
            return [{'id':str(row['id']),'kind':'discovery','input':json.loads(row['input_json']),'text_hash':row['input_hash']}]
    return []

def complete_job(body):
    ident=str(body.get('id',''));digest=str(body.get('text_hash',''));kind=body.get('kind')
    with DB() as c:
        c.execute('BEGIN IMMEDIATE')
        if body.get('error'):
            if kind=='summary':c.execute("UPDATE summaries SET status='queued',next_at=?,message='KI-Verarbeitung wird erneut versucht.' WHERE video_id=? AND text_hash=?",(time.time()+1800,ident,digest))
            elif kind=='discovery':c.execute("UPDATE discovery_runs SET status='queued',next_at=?,message='KI-Auswahl wird erneut versucht.' WHERE id=? AND input_hash=?",(time.time()+1800,ident,digest))
            return 0
        if kind=='summary':
            text=body.get('text_de','')
            if not isinstance(text,str) or not 50<=len(text.strip())<=6000:raise ValueError('Ungültige Zusammenfassung.')
            return c.execute("UPDATE summaries SET status='ready',text_de=?,next_at=0,message='',updated_at=? WHERE video_id=? AND text_hash=? AND status='working'",
                             (text.strip(),UTC(),ident,digest)).rowcount
        if kind!='discovery':raise ValueError('Unbekannte KI-Aufgabe.')
        row=c.execute("SELECT * FROM discovery_runs WHERE id=? AND input_hash=? AND status='working'",(ident,digest)).fetchone()
        if not row:return 0
        source=json.loads(row['input_json']);items={i['id']:i for i in source['candidates']}
        selections=body.get('selections',[])
        if not isinstance(selections,list) or len(selections)>source['limit']:raise ValueError('Zu viele Vorschläge.')
        config=settings();saved=0;seen=set()
        for selected in selections:
            item=items.get(selected.get('id')) if isinstance(selected,dict) else None
            reason=selected.get('reason','') if isinstance(selected,dict) else ''
            if not item or item['id'] in seen or not isinstance(reason,str) or not 20<=len(reason)<=800:raise ValueError('Ungültiger Vorschlag.')
            seen.add(item['id'])
            if not config['enabled'] or item['platform'] not in config['platforms'] or not allowed_candidate(c,item,config):continue
            saved+=c.execute('''INSERT OR IGNORE INTO suggestions(id,run_id,platform,handle,creator,profile_url,url,title,evidence,reason,published_at,topic,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(item['id'],ident,item['platform'],item['handle'],item['creator'],item['profile_url'],item['url'],
                item['title'],item['evidence'],reason,item['published_at'],item['topic'],UTC())).rowcount
        c.execute("UPDATE discovery_runs SET status='ready',finished_at=?,message=? WHERE id=?",(UTC(),str(saved)+(' geprüfter Vorschlag.' if saved==1 else ' geprüfte Vorschläge.'),ident))
        return saved

def discovery_status():
    with DB() as c:
        runs=[dict(r) for r in c.execute('SELECT id,slot,started_at,finished_at,status,message,platforms_json FROM discovery_runs ORDER BY id DESC LIMIT 5')]
        muted=[dict(r) for r in c.execute('SELECT * FROM muted_creators')]
    for r in runs:r['platforms']=json.loads(r.pop('platforms_json'))
    return {'settings':settings(),'runs':runs,'muted_creators':muted,'refreshing':BUSY,'cadence':'UTC-Zeitfenster: täglich oder alle zwölf Stunden; erster Lauf beim Start.'}

def suggestions():
    config=settings()
    with DB() as c:
        rows=[dict(r) for r in c.execute("""SELECT s.*,COALESCE(d.status,'pending') AS content_status,
          COALESCE(d.message,'') AS content_message,COALESCE(d.language,'') AS language
          FROM suggestions s LEFT JOIN discovery_content d ON d.suggestion_id=s.id
          WHERE s.state='new' ORDER BY s.run_id DESC,s.created_at DESC LIMIT 30""")]
        return [r for r in rows if r['platform'] in config['platforms'] and not c.execute(
          'SELECT 1 FROM muted_creators WHERE platform=? AND handle=?',(r['platform'],r['handle'])).fetchone()
          and not c.execute('SELECT 1 FROM sources WHERE platform=? AND (lower(handle)=lower(?) OR channel_id=?)',(r['platform'],r['handle'],r['handle'])).fetchone()
          and not any(x.casefold() in (r['title']+' '+r['evidence']).casefold() for x in config['exclude'])]

def feedback(body):
    state=body.get('action')
    if state not in ('dismiss','mute','subscribe'):raise ValueError('Ungültige Rückmeldung.')
    with DB() as c:
        row=c.execute('SELECT * FROM suggestions WHERE id=?',(str(body.get('id','')),)).fetchone()
        if not row:raise ValueError('Vorschlag nicht gefunden.')
        if state=='mute':block_creator(c,row['platform'],row['handle'],row['creator'])
        if state=='subscribe':
            unblock_creator(c,row['platform'],row['handle'])
            return subscribe_creator(c,row)
        c.execute('UPDATE suggestions SET state=? WHERE id=?',(state,row['id']))

def block_creator(c,platform,handle,title):
    sources=c.execute('SELECT id,enabled FROM sources WHERE platform=? AND (lower(handle)=lower(?) OR channel_id=?)',(platform,handle,handle)).fetchall()
    old=c.execute('SELECT resume_json FROM muted_creators WHERE platform=? AND handle=?',(platform,handle)).fetchone()
    resume=set(json.loads(old[0])) if old else set()
    resume.update(row['id'] for row in sources if row['enabled'])
    c.execute('''INSERT INTO muted_creators(platform,handle,title,resume_json) VALUES(?,?,?,?)
      ON CONFLICT(platform,handle) DO UPDATE SET title=excluded.title,resume_json=excluded.resume_json''',(platform,handle,title,json.dumps(sorted(resume))))
    c.execute('UPDATE sources SET enabled=0 WHERE platform=? AND (lower(handle)=lower(?) OR channel_id=?)',(platform,handle,handle))
    c.execute("UPDATE suggestions SET state='mute' WHERE platform=? AND lower(handle)=lower(?)",(platform,handle))

def unblock_creator(c,platform,handle):
    old=c.execute('SELECT resume_json FROM muted_creators WHERE platform=? AND handle=?',(platform,handle)).fetchone()
    if old:
        for ident in json.loads(old[0]):c.execute('UPDATE sources SET enabled=1,next_at=0 WHERE id=? AND platform=? AND (lower(handle)=lower(?) OR channel_id=?)',(ident,platform,handle,handle))
    c.execute('DELETE FROM muted_creators WHERE platform=? AND handle=?',(platform,handle))
    c.execute("UPDATE suggestions SET state='new' WHERE platform=? AND lower(handle)=lower(?) AND state='mute'",(platform,handle))

def creator_block(body):
    if type(body.get('blocked',True)) is not bool:raise ValueError('Ungültiger Sperrstatus.')
    blocked=body.get('blocked',True)
    with DB() as c:
        c.execute('BEGIN IMMEDIATE')
        if body.get('suggestion_id'):
            row=c.execute('SELECT platform,handle,creator AS title FROM suggestions WHERE id=?',(str(body['suggestion_id']),)).fetchone()
        elif body.get('source_id'):
            row=c.execute('SELECT platform,COALESCE(channel_id,handle) AS handle,title FROM sources WHERE id=?',(int(body['source_id']),)).fetchone()
        elif not blocked:
            row=c.execute('SELECT platform,handle,title FROM muted_creators WHERE platform=? AND handle=?',(str(body.get('platform','')),str(body.get('handle','')))).fetchone()
        else:row=None
        if not row:raise ValueError('Creator nicht gefunden.')
        if blocked:block_creator(c,row['platform'],row['handle'],row['title'])
        else:unblock_creator(c,row['platform'],row['handle'])
    return {'ok':True,'blocked':blocked,'title':row['title']}

def subscribe_creator(c,row):
    source=c.execute('SELECT * FROM sources WHERE platform=? AND (lower(handle)=lower(?) OR channel_id=?)',
                     (row['platform'],row['handle'],row['handle'])).fetchone()
    if not source:
        mode='posts' if row['platform']=='x' else 'both' if row['platform']=='youtube' else 'short'
        ident=c.execute('''INSERT INTO sources(platform,handle,title,channel_id,mode,delivery) VALUES(?,?,?,?,?,?)''',
          (row['platform'],row['handle'],row['creator'],row['handle'] if row['platform']=='youtube' else None,mode,'news' if row['platform']=='x' else 'videos')).lastrowid
        source=c.execute('SELECT * FROM sources WHERE id=?',(ident,)).fetchone()
    content=c.execute('SELECT * FROM discovery_content WHERE suggestion_id=?',(row['id'],)).fetchone()
    if content and content['status']=='ready':
        if content['kind']=='news':
            c.execute('''INSERT INTO posts(id,source_id,external_id,author,text,url,published_at,media_json,discovered_at,
              text_de,text_hash,translation_status,seen,favorite) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              seen=max(posts.seen,excluded.seen),favorite=max(posts.favorite,excluded.favorite)''',
              ('x:'+str(source['id'])+':'+content['external_id'],source['id'],content['external_id'],row['handle'],content['text'],
               content['url'],row['published_at'],content['media_json'],UTC(),content['text_de'],content['text_hash'],content['translation_status'],content['seen'],content['favorite']))
        elif content['format'] in ('long','short'):
            c.execute('''INSERT INTO videos(id,source_id,external_id,platform,format,title,url,thumbnail,published_at,discovered_at,seen,favorite,feed_eligible)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET seen=max(videos.seen,excluded.seen),favorite=max(videos.favorite,excluded.favorite)''',
              (row['platform']+':'+content['external_id'],source['id'],content['external_id'],row['platform'],content['format'],content['title'],
               content['url'],content['thumbnail'],row['published_at'],UTC(),content['seen'],content['favorite']))
    c.execute("UPDATE suggestions SET state='subscribe' WHERE id=?",(row['id'],))
    return {'id':source['id'],'title':source['title'],'platform':source['platform'],'handle':source['handle']}

def favorite_creator(c,ident):
    if ident.startswith('discovery:'):
        row=c.execute('SELECT s.* FROM suggestions s JOIN discovery_content d ON d.suggestion_id=s.id WHERE s.id=? AND d.status=\'ready\' AND s.state IN (\'new\',\'subscribe\')',
                      (ident.split(':',1)[1],)).fetchone()
    elif ':' in ident:
        row=c.execute('''SELECT s.* FROM suggestions s JOIN discovery_content d ON d.suggestion_id=s.id
          WHERE d.platform=? AND d.external_id=? AND d.status='ready' AND s.state IN ('new','subscribe')''',
          (ident.split(':',1)[0],ident.rsplit(':',1)[1])).fetchone()
    else:row=None
    return subscribe_creator(c,row) if row else None

def summary_status():
    with DB() as c:return [dict(r) for r in c.execute('''SELECT j.video_id,j.status,j.message,j.updated_at,j.basis,j.next_at,v.title,s.title AS creator
      FROM summaries j JOIN videos v ON v.id=j.video_id JOIN sources s ON s.id=v.source_id ORDER BY v.published_at DESC LIMIT 100''')]

def summary_news(source_id=0,unseen=False):
    with DB() as c:
        rows=[dict(r) for r in c.execute('''SELECT 'summary:'||v.id AS id,v.id AS video_id,v.source_id,v.external_id,
          v.title,s.title AS creator,s.handle,v.url,v.published_at,v.seen,v.favorite,v.thumbnail,j.text_de,
          'video_summary' AS kind,'ready' AS translation_status,j.basis AS basis
          FROM summaries j JOIN videos v ON v.id=j.video_id JOIN sources s ON s.id=v.source_id
          WHERE j.status='ready' AND s.enabled=1 AND s.delivery IN ('news','both')
          AND (?=0 OR s.id=?) AND (?=0 OR v.seen=0)''',(source_id,source_id,int(unseen)))]
    for row in rows:
        thumbnail=row.pop('thumbnail');row.update(text='',media=[thumbnail] if thumbnail else [],author=row['creator'])
    return rows

def video_metadata(url):
    """Inspect audio-language metadata only. No audio/video download and no browser credentials."""
    if not re.fullmatch(r'https://www.youtube.com/watch\?v=[\w-]{11}|https://www.tiktok.com/@[\w.]{2,24}/video/\d{15,25}',url):
        raise ValueError('Ungültige Video-Adresse.')
    home=DATA()/'reach'
    env={**os.environ,'HOME':str(home),'USERPROFILE':str(home)}
    args=[sys.executable,'-m','yt_dlp','--ignore-config','--skip-download','--no-playlist',
          '--no-warnings','--socket-timeout','25','--retries','0','-f','bestaudio/best', '--dump-single-json','--',url]
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=100,env=env)
        if p.returncode or len(p.stdout)>10000000:raise ValueError()
        data=json.loads(p.stdout)
    except Exception:raise ValueError('Videometadaten derzeit nicht verfügbar.') from None
    language=str(data.get('language') or '')
    # The selected best-audio format's language is metadata about the audio, not a title-language guess.
    if not language:
        audio=[f for f in data.get('requested_formats',[]) if f.get('acodec')!='none' and f.get('language')]
        if len(audio)==1:language=str(audio[0]['language'])
    return {'language':language.lower().split('-')[0].split('_')[0], 'language_basis':'Sprache der Audiospur laut Videometadaten' if language else '',
            'thumbnail':str(data.get('thumbnail') or ''),'duration':data.get('duration') or 0,
            'title':str(data.get('title') or ''),'description':str(data.get('description') or '')[:30000],
            'creator':str(data.get('uploader') or data.get('channel') or ''),'channel_id':str(data.get('channel_id') or ''),
            'published_at':parsed_date(str(data.get('upload_date') or ''))}

def hydrate_one(item):
    if item['platform']=='x':
        ident=item['url'].rsplit('/',1)[-1]
        rows=PARSE_X(reach('twitter','thread',item['url']),item['handle'])
        row=next((r for r in rows if r['external_id']==ident),None)
        if not row:raise ValueError('Der vollständige Originalbeitrag ist derzeit nicht verfügbar.')
        return {'external_id':ident,'kind':'news','format':'','title':'','url':row['url'],'thumbnail':'',
          'text':row['text'],'media':row['media'],'language':'','language_basis':''}
    if item['platform']=='tiktok':return tiktok.hydrate(item)
    metadata=video_metadata(item['url'])
    if metadata['language']!='de':
        return {'external_id':'','kind':'video','format':'','title':item['title'],'url':item['url'],'thumbnail':'',
                'text':'','media':[],**metadata,'status':'language_unconfirmed',
                'message':'Nur Videos mit bestätigter deutscher Audiosprache werden im Video-Feed angezeigt.'}
    if item['platform']=='tiktok':ident=item['url'].rsplit('/',1)[-1];kind='short'
    else:
        ident=urllib.parse.parse_qs(urllib.parse.urlsplit(item['url']).query).get('v',[''])[0];kind=''
        for tab,fmt in [('shorts','short'),('videos','long')]:
            try:rows,_=PARSE_TAB(PUBLIC(item['profile_url']+'/'+tab),fmt)
            except Exception:continue
            if any(v['external_id']==ident for v in rows):kind=fmt;break
        if not kind:raise ValueError('Das Videoformat konnte noch nicht bestätigt werden.')
    return {'external_id':ident,'kind':'video','format':kind,'title':item['title'],'url':item['url'],
            'text':'','media':[],**metadata}

def hydrate_suggestions():
    if not settings()['enabled']:return
    items=suggestions()
    attempted=0
    for item in items[:30]:
        with DB() as c:
            row=c.execute('SELECT * FROM discovery_content WHERE suggestion_id=?',(item['id'],)).fetchone()
            if row and (row['status']=='ready' or row['next_at']>time.time()):continue
        if attempted>=3:break
        attempted+=1
        try:
            data=hydrate_one(item);text=data['text'];digest=hashlib.sha256(text.encode()).hexdigest()
            with DB() as c:c.execute('''INSERT INTO discovery_content(suggestion_id,platform,external_id,kind,format,title,url,
              thumbnail,text,text_hash,media_json,language,language_basis,status,message,next_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(suggestion_id) DO UPDATE SET
              external_id=excluded.external_id,kind=excluded.kind,format=excluded.format,title=excluded.title,
              url=excluded.url,thumbnail=excluded.thumbnail,text=excluded.text,text_hash=excluded.text_hash,
              media_json=excluded.media_json,language=excluded.language,language_basis=excluded.language_basis,
              text_de=CASE WHEN discovery_content.text_hash=excluded.text_hash THEN discovery_content.text_de ELSE '' END,
              translation_status=CASE WHEN discovery_content.text_hash=excluded.text_hash THEN discovery_content.translation_status ELSE 'pending' END,
              status=excluded.status,message=excluded.message,next_at=excluded.next_at,updated_at=excluded.updated_at''',
              (item['id'],item['platform'],data['external_id'],data['kind'],data['format'],data['title'],data['url'],data['thumbnail'],
               text,digest,json.dumps(data['media']),data['language'],data['language_basis'],data.get('status','ready'),
               data.get('message',''),time.time()+21600 if data.get('status') else 0,UTC()))
        except Exception:
            with DB() as c:c.execute('''INSERT INTO discovery_content(suggestion_id,platform,external_id,kind,url,status,message,next_at,updated_at)
              VALUES(?,?,'','news',?,'error',?,?,?) ON CONFLICT(suggestion_id) DO UPDATE SET
              status='error',message=excluded.message,next_at=excluded.next_at,updated_at=excluded.updated_at''',
              (item['id'],item['platform'],item['url'],'Originalinhalt konnte noch nicht vollständig geprüft werden.',time.time()+21600,UTC()))

def claim_discovery_translations(c,limit):
    if limit<=0 or not settings()['enabled']:return []
    rows=[dict(r) for r in c.execute('''SELECT 'discovery:'||d.suggestion_id AS id,d.text,d.text_hash
      FROM discovery_content d JOIN suggestions s ON s.id=d.suggestion_id WHERE s.state='new' AND d.kind='news'
      AND d.status='ready' AND d.translation_status!='ready' AND d.translation_next_at<=? LIMIT ?''',(time.time(),limit))]
    for row in rows:c.execute("UPDATE discovery_content SET translation_status='working',translation_next_at=? WHERE suggestion_id=?",(time.time()+240,row['id'].split(':',1)[1]))
    return rows

def complete_discovery_translation(c,ident,digest,text):
    if text.strip():return c.execute("UPDATE discovery_content SET text_de=?,translation_status='ready',translation_next_at=0 WHERE suggestion_id=? AND text_hash=?",(text.strip(),ident,digest)).rowcount
    c.execute("UPDATE discovery_content SET translation_status='error',translation_next_at=? WHERE suggestion_id=? AND text_hash=?",(time.time()+900,ident,digest));return 0

def discovery_rows():
    if not settings()['enabled']:return []
    eligible={s['id'] for s in suggestions()}
    with DB() as c:
        rows=[dict(r) for r in c.execute('''SELECT d.*,s.creator,s.handle,s.published_at,s.reason FROM discovery_content d
          JOIN suggestions s ON s.id=d.suggestion_id WHERE d.status='ready' ORDER BY s.published_at DESC''')]
    return [r for r in rows if r['suggestion_id'] in eligible]

def discovery_news(unseen=False):
    result=[]
    for row in discovery_rows():
        if row['kind']!='news' or (unseen and row['seen']):continue
        row.update(id='discovery:'+row['suggestion_id'],source_id=0,kind='x',author=row['handle'],
                   is_discovery=True,basis='Originalbeitrag',media=json.loads(row.pop('media_json')))
        result.append(row)
    return result

def discovery_feed(kind,platform='',unseen=True):
    rows=[]
    for row in discovery_rows():
        if row['kind']!='video' or row['format']!=kind or row['language']!='de' or (unseen and row['seen']):continue
        if platform and row['platform']!=platform:continue
        row.update(id=row['platform']+':'+row['external_id'],source_id=0,is_discovery=True,duration='')
        rows.append(row)
    return rows

def mark_discovery(c,ident,key,value):
    if key not in ('seen','favorite'):raise ValueError('Ungültiger Inhaltsstatus.')
    if ident.startswith('discovery:'):
        c.execute('UPDATE discovery_content SET '+key+'=? WHERE suggestion_id=?',(value,ident.split(':',1)[1]))
        row=c.execute('SELECT platform,external_id FROM discovery_content WHERE suggestion_id=?',(ident.split(':',1)[1],)).fetchone()
        if row and row['platform']=='x':c.execute('UPDATE posts SET '+key+'=? WHERE external_id=?',(value,row['external_id']))
    else:
        if ':' in ident:c.execute('UPDATE discovery_content SET '+key+'=? WHERE platform=? AND external_id=?',(value,ident.split(':',1)[0],ident.rsplit(':',1)[1]))

def preserve_discovery_state(c,platform,external_id):
    row=c.execute('SELECT max(seen),max(favorite) FROM discovery_content WHERE platform=? AND external_id=?',(platform,external_id)).fetchone()
    return (int(row[0] or 0),int(row[1] or 0))
