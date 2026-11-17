"""KI Social Media. Standard-library service; metadata only, official embedded players."""
from __future__ import annotations
import concurrent.futures, contextlib, datetime as dt, hashlib, hmac, html, json
import os, pathlib, re, secrets, sqlite3, subprocess, threading, time, urllib.parse, urllib.request, importlib.util
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque

VERSION = '0.1.0-beta.1'
AI_ENABLED = os.environ.get('AI_ENABLED', 'false').lower() == 'true'
UA = 'Mozilla/5.0'
DATA = pathlib.Path(os.environ.get('CODY_DATA', pathlib.Path(__file__).parent.parent / 'data'))
TOKEN = os.environ.get('CODY_API_TOKEN', '')
TRANSLATOR_TOKEN = os.environ.get('CODY_TRANSLATOR_TOKEN','')
SPEECH_TOKEN = os.environ.get('CODY_SPEECH_TOKEN','')
PAIR = os.environ.get('CODY_PAIR_CODE', '')
PAIR_EXPIRES = float(os.environ.get('CODY_PAIR_EXPIRES', '0'))
JOB_LOCK = threading.Lock()
RUNNING = False
LAST_MANUAL = 0.0
PAIR_ATTEMPTS: dict[str, list[float]] = {}
X_LOCK = threading.Lock()
_news_spec=importlib.util.spec_from_file_location('cody_newsroom',pathlib.Path(__file__).with_name('newsroom.py'))
newsroom=importlib.util.module_from_spec(_news_spec);_news_spec.loader.exec_module(newsroom)

def pairing():
    try:
        value=json.loads((DATA/'pairing.json').read_text())
        return str(value['code']),float(value['expires'])
    except (OSError,ValueError,KeyError,TypeError):return PAIR,PAIR_EXPIRES

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()

@contextlib.contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / 'cody-social.db', timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally: conn.close()

def initialize():
    newsroom.DB=db;newsroom.DATA=lambda:DATA;newsroom.UTC=utc;newsroom.PUBLIC=get_public;newsroom.X_LOCK=X_LOCK
    newsroom.PARSE_X=parse_x_items;newsroom.PARSE_TAB=parse_youtube_tab
    newsroom.TIKTOK_RAW=_get_public
    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY, platform TEXT NOT NULL, handle TEXT NOT NULL,
          title TEXT NOT NULL, channel_id TEXT, mode TEXT NOT NULL, enabled INTEGER DEFAULT 1,
          status TEXT DEFAULT 'pending', message TEXT DEFAULT '', checked_at TEXT,
          success_at TEXT, next_at REAL DEFAULT 0, failures INTEGER DEFAULT 0,
          UNIQUE(platform,handle));
        CREATE TABLE IF NOT EXISTS videos (
          id TEXT PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          external_id TEXT NOT NULL, platform TEXT NOT NULL, format TEXT NOT NULL,
          title TEXT NOT NULL, url TEXT NOT NULL, thumbnail TEXT DEFAULT '',
          published_at TEXT, duration TEXT DEFAULT '', discovered_at TEXT NOT NULL,
          seen INTEGER DEFAULT 0, favorite INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS video_feed ON videos(format,published_at DESC);
        CREATE TABLE IF NOT EXISTS posts (
          id TEXT PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          external_id TEXT NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL, url TEXT NOT NULL,
          published_at TEXT NOT NULL, media_json TEXT NOT NULL DEFAULT '[]', discovered_at TEXT NOT NULL,
          seen INTEGER DEFAULT 0, favorite INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS post_feed ON posts(published_at DESC);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, successful INTEGER, failed INTEGER);
        CREATE TABLE IF NOT EXISTS feed_windows (
          source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          format TEXT NOT NULL, initialized_at TEXT NOT NULL, PRIMARY KEY(source_id,format));
        ''')
        columns={r['name'] for r in c.execute('PRAGMA table_info(videos)')}
        if 'feed_eligible' not in columns:c.execute('ALTER TABLE videos ADD COLUMN feed_eligible INTEGER NOT NULL DEFAULT 1')
        post_columns={r['name'] for r in c.execute('PRAGMA table_info(posts)')}
        for name,definition in {'text_de':"TEXT NOT NULL DEFAULT ''",'text_hash':"TEXT NOT NULL DEFAULT ''",
          'translation_status':"TEXT NOT NULL DEFAULT 'pending'",'translation_attempts':'INTEGER NOT NULL DEFAULT 0',
          'translation_next_at':'REAL NOT NULL DEFAULT 0','link_only':'INTEGER NOT NULL DEFAULT 0'}.items():
            if name not in post_columns:c.execute('ALTER TABLE posts ADD COLUMN '+name+' '+definition)
        if not c.execute("SELECT 1 FROM meta WHERE key='finite-feed-v1'").fetchone():
            c.execute('UPDATE videos SET feed_eligible=0')
            for group in c.execute('SELECT DISTINCT source_id,format FROM videos').fetchall():
                newest=c.execute('''SELECT id FROM videos WHERE source_id=? AND format=?
                  ORDER BY (published_at IS NULL),published_at DESC,discovered_at DESC,rowid ASC LIMIT 5''',tuple(group)).fetchall()
                c.executemany('UPDATE videos SET feed_eligible=1 WHERE id=?',[(r['id'],) for r in newest])
            c.execute("INSERT INTO meta VALUES('finite-feed-v1',?)",(utc(),))
        for row in c.execute("SELECT id,text FROM posts WHERE text_hash='' OR text_hash IS NULL").fetchall():
            c.execute('UPDATE posts SET text_hash=?,link_only=? WHERE id=?',
              (hashlib.sha256(row['text'].encode()).hexdigest(),int(not has_story_text(row['text'])),row['id']))
        if not c.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
            for s in json.loads(pathlib.Path(__file__).with_name('seed.json').read_text(encoding='utf-8')):
                c.execute('INSERT OR IGNORE INTO sources(platform,handle,title,channel_id,mode) VALUES(?,?,?,?,?)',
                          (s['platform'],s['handle'],s['title'],s.get('channel_id'),s['mode']))
            c.execute("INSERT INTO meta VALUES('seeded','1')")
    # executescript in migrations owns its transaction; run after the original migration commits.
    with db() as c:newsroom.initialize(c)
    newsroom.repair_initial_x_identity()

def get_public(url):
    match=re.fullmatch(r'https://www\.tiktok\.com/embed/@([A-Za-z0-9_.]{2,24})',url)
    if match:return newsroom.tiktok.profile(match[1])
    return _get_public(url)

def _get_public(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.youtube.com','www.tiktok.com'} or parsed.username or parsed.port:
        raise ValueError('Nur öffentliche YouTube- und TikTok-Adressen werden abgerufen.')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            p = urllib.parse.urlsplit(newurl)
            if p.scheme != 'https' or p.hostname not in {'youtube.com','www.youtube.com','m.youtube.com','consent.youtube.com','www.tiktok.com','tiktok.com'} or p.username or p.port:
                raise ValueError('Die Plattform hat auf eine nicht unterstützte Adresse umgeleitet: '+str(p.hostname))
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url,headers={'User-Agent':UA}),timeout=25) as r:
        data = r.read(6_000_001)
        if len(data)>6_000_000: raise ValueError('Plattformantwort zu groß.')
        return data.decode('utf-8','replace')

def youtube_state(body):
    for marker in ['var ytInitialData = ', 'window["ytInitialData"] = ', 'ytInitialData = ']:
        at=body.find(marker)
        if at>=0:
            try: return json.JSONDecoder().raw_decode(body[at+len(marker):])[0]
            except ValueError: pass
    raise ValueError('YouTube-Seite enthält keine auswertbare Kanalliste.')

def deep_values(value, key):
    if isinstance(value,dict):
        if key in value: yield value[key]
        for v in value.values(): yield from deep_values(v,key)
    elif isinstance(value,list):
        for v in value: yield from deep_values(v,key)

def parse_youtube_tab(body, kind):
    state=youtube_state(body)
    tabs=state.get('contents',{}).get('twoColumnBrowseResultsRenderer',{}).get('tabs',[])
    selected=next((t['tabRenderer'] for t in tabs if t.get('tabRenderer',{}).get('selected')),None)
    if selected is None: raise ValueError('YouTube-Kanalreiter wurde nicht gefunden.')
    content=selected.get('content',{})
    result={}
    if kind=='long':
        models=list(deep_values(content,'lockupViewModel'))
        for v in models:
            if v.get('contentType')!='LOCKUP_CONTENT_TYPE_VIDEO': continue
            ident=v.get('contentId','')
            badges=list(deep_values(v.get('contentImage',{}),'thumbnailBadgeViewModel'))
            result[ident]={'external_id':ident,'format':'long',
                'title':v.get('metadata',{}).get('lockupMetadataViewModel',{}).get('title',{}).get('content',''),
                'duration':next((b.get('text','') for b in badges if re.fullmatch(r'[\d:]+',b.get('text',''))),'')}
        for v in deep_values(content,'videoRenderer'):
            ident=v.get('videoId','');t=v.get('title',{})
            result[ident]={'external_id':ident,'format':'long','title':t.get('simpleText') or ''.join(x.get('text','') for x in t.get('runs',[])),
                          'duration':v.get('lengthText',{}).get('simpleText','')}
    else:
        for key in ['shortsLockupViewModel','reelItemRenderer']:
            for v in deep_values(content,key):
                candidates=[v.get('videoId',''),v.get('contentId','')]
                candidates+=list(deep_values(v,'videoId'))
                candidates+=[m.group(1) for u in deep_values(v,'url') if isinstance(u,str) for m in [re.search(r'(?:/vi/|/shorts/)([\w-]{11})(?:[/?]|$)',u)] if m]
                ident=next((i for i in candidates if isinstance(i,str) and re.fullmatch(r'[\w-]{11}',i)),None)
                if not ident: continue
                title=v.get('overlayMetadata',{}).get('primaryText',{}).get('content','')
                if not title:
                    t=v.get('headline',{});title=t.get('simpleText') or ''.join(x.get('text','') for x in t.get('runs',[]))
                result[ident]={'external_id':ident,'format':'short','title':title or 'YouTube Short','duration':''}
    for ident,v in list(result.items()):
        if not re.fullmatch(r'[\w-]{11}',ident): del result[ident];continue
        v.update(url='https://www.youtube.com/watch?v='+ident, thumbnail='https://i.ytimg.com/vi/'+ident+'/hqdefault.jpg')
    # An explicitly empty Videos/Shorts tab is valid; unknown layouts must not silently clear data.
    if not result and not list(deep_values(content,'messageRenderer')):
        raise ValueError('YouTube hat keine unterstützten Videokarten geliefert; vorhandene Videos bleiben erhalten.')
    return list(result.values()),state.get('metadata',{}).get('channelMetadataRenderer',{})

def parse_rss(body):
    root=ET.fromstring(body);ns={'a':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}
    return {v.findtext('yt:videoId',namespaces=ns):{'published_at':v.findtext('a:published',namespaces=ns),
             'title':v.findtext('a:title',namespaces=ns)} for v in root.findall('a:entry',ns)}

def parse_tiktok(body,handle):
    data=newsroom.tiktok.parse_profile(body,handle)
    user=data.get('userInfo',{})
    if data.get('isError') or user.get('privateAccount') or user.get('code') not in (None,0,200):
        raise ValueError('Dieses TikTok-Profil ist derzeit nicht öffentlich abrufbar.')
    if 'videoList' not in data: raise ValueError('TikTok-Profilliste fehlt.')
    videos=[]
    for v in data['videoList']:
        ident=str(v.get('id',''));author=v.get('authorUniqueId',handle)
        if not re.fullmatch(r'\d{15,25}',ident) or author.lower()!=handle.lower(): continue
        videos.append({'external_id':ident,'format':'short','title':v.get('desc') or 'TikTok von @'+author,
            'url':'https://www.tiktok.com/@'+author+'/video/'+ident,'thumbnail':v.get('coverUrl',''),
            'published_at':dt.datetime.fromtimestamp(int(ident)>>32,dt.timezone.utc).isoformat(),'duration':''})
    return videos,user.get('nickname') or handle

def parse_x_items(items, handle):
    if not isinstance(items,list):raise ValueError('X hat kein unterstütztes Beitragsformat geliefert.')
    posts={}
    for item in items[:50]:
        if not isinstance(item,dict):continue
        raw=item.get('raw') if isinstance(item.get('raw'),dict) else {}
        url=item.get('url') or raw.get('url') or ''
        match=re.fullmatch(r'https://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})/status/(\d{15,25})(?:[/?#].*)?',str(url))
        ident=match[2] if match else str(raw.get('id') or raw.get('tweet_id') or '')
        if not re.fullmatch(r'\d{15,25}',ident):continue
        # A snowflake carries the actual publication time, including for pinned posts.
        try:published=dt.datetime.fromtimestamp(((int(ident)>>22)+1288834974657)/1000,dt.timezone.utc).isoformat()
        except (ValueError,OverflowError,OSError):continue
        text=item.get('text') or raw.get('text') or raw.get('content') or item.get('title') or ''
        if not isinstance(text,str) or not text.strip():continue
        author=match[1] if match and match[1].lower()!='i' else handle
        media=[]
        for key in ('images','photos','media','media_urls'):
            values=raw.get(key,[])
            if not isinstance(values,list):continue
            for entry in values[:4]:
                candidate=entry if isinstance(entry,str) else entry.get('url') or entry.get('media_url_https') or entry.get('thumbnail','') if isinstance(entry,dict) else ''
                if not isinstance(candidate,str):continue
                try:p=urllib.parse.urlsplit(candidate)
                except ValueError:continue
                if p.scheme=='https' and p.hostname=='pbs.twimg.com' and not p.username and not p.port and candidate not in media:media.append(candidate)
        posts[ident]={'external_id':ident,'author':author,'text':text.strip()[:30000],
            'url':'https://x.com/'+author+'/status/'+ident,'published_at':published,'media':media[:4]}
    if items and not posts:raise ValueError('X hat keine auswertbaren Beiträge geliefert; gespeicherte Beiträge bleiben erhalten.')
    return list(posts.values())


def collect_x(source):
    home=DATA/'reach'
    binary=pathlib.Path(os.environ.get('CODY_REACH_BIN',str(home/'venv/bin/agent-reach')))
    if not binary.is_file():raise ValueError('Die X-Anbindung ist auf dem Server noch nicht eingerichtet.')
    env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'PYTHONUNBUFFERED':'1'}
    try:
        with X_LOCK:
            result=subprocess.run([str(binary),'twitter','tweets',source['handle'],'--limit','25','--timeout','70'],
                                  env=env,capture_output=True,text=True,timeout=120)
    except subprocess.TimeoutExpired:raise ValueError('X antwortet gerade zu langsam. Cody versucht es später erneut.') from None
    except OSError:raise ValueError('Die X-Anbindung konnte auf dem Server nicht gestartet werden.') from None
    # Never expose upstream stderr/stdout: a browser tool could include session data.
    if len(result.stdout)>3_000_000:raise ValueError('Die X-Antwort ist zu groß.')
    try:payload=json.loads(result.stdout)
    except ValueError:raise ValueError('X hat gerade keine lesbare Antwort geliefert.') from None
    if not isinstance(payload,dict):raise ValueError('X hat gerade keine lesbare Antwort geliefert.')
    if result.returncode or not payload.get('ok'):
        code=(payload.get('error') or {}).get('code','')
        messages={'NEED_LOGIN':'Die X-Anmeldung auf dem Server fehlt oder ist abgelaufen. Bitte am PC erneut verbinden.',
          'PLATFORM_BLOCKED':'X verlangt eine persönliche Prüfung der Anmeldung. Bitte am PC prüfen.',
          'RATE_LIMITED':'X begrenzt gerade die Abrufe. Cody wartet vor dem nächsten Versuch.',
          'NEED_SETUP':'Die X-Anbindung auf dem Server benötigt eine Prüfung.',
          'BUSY':'Die X-Anbindung ist gerade beschäftigt. Cody versucht es später erneut.'}
        raise ValueError(messages.get(code,'X ist gerade nicht abrufbar. Gespeicherte Beiträge bleiben verfügbar.'))
    return parse_x_items(payload.get('items'),source['handle']),{'title':source['title']},[]


def collect(source):
    if source['platform']=='rss':return newsroom.collect_rss(source)
    if source['platform']=='x':return collect_x(source)
    if source['platform']=='tiktok':
        videos,title=parse_tiktok(get_public('https://www.tiktok.com/embed/@'+source['handle']),source['handle'])
        return videos,{'title':title},[]
    root='https://www.youtube.com/'+('channel/'+source['channel_id'] if source['handle']==source['channel_id'] else '@'+urllib.parse.quote(source['handle']))
    videos=[];metadata={};warnings=[]
    kinds=['long','short'] if source['mode']=='both' else [source['mode']]
    for kind in kinds:
        try:
            found,meta=parse_youtube_tab(get_public(root+('/videos' if kind=='long' else '/shorts')),kind)
            videos+=found;metadata.update(meta)
        except Exception as e: warnings.append(('Lange Videos: ' if kind=='long' else 'Shorts: ')+str(e))
    if not videos and warnings: raise ValueError(' '.join(warnings))
    channel_id=metadata.get('externalId') or source['channel_id']
    if channel_id:
        try:
            rss=parse_rss(get_public('https://www.youtube.com/feeds/videos.xml?channel_id='+channel_id))
            for v in videos:
                if v['external_id'] in rss: v.update({k:x for k,x in rss[v['external_id']].items() if x})
        except Exception as e: warnings.append('RSS: '+str(e))
    return videos,{'title':metadata.get('title') or source['title'],'channel_id':channel_id},warnings

def save_success(source,videos,meta,warnings):
    now=utc(); interval=3600 if source['platform']=='tiktok' else 1800
    with db() as c:
        first_kinds={v['format'] for v in videos if source['platform'] not in ('x','rss') and not c.execute(
            'SELECT 1 FROM feed_windows WHERE source_id=? AND format=?',(source['id'],v['format'])).fetchone()}
        initial_selection={}
        for kind in first_kinds:
            ordered=[v for v in videos if v['format']==kind]
            ordered=sorted(enumerate(ordered),key=lambda pair:(bool(pair[1].get('published_at')),pair[1].get('published_at') or '',-pair[0]),reverse=True)
            initial_selection[kind]={v['external_id'] for _,v in ordered[:5]}
            c.execute('UPDATE videos SET feed_eligible=0 WHERE source_id=? AND format=?',(source['id'],kind))
        for v in videos:
            if source['platform']=='rss':
                newsroom.save_rss(c,source,[v],now);continue
            if source['platform']=='x':
                digest=hashlib.sha256(v['text'].encode()).hexdigest()
                c.execute('''INSERT INTO posts(id,source_id,external_id,author,text,url,published_at,media_json,discovered_at,text_hash,link_only)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                  author=excluded.author,url=excluded.url,published_at=excluded.published_at,media_json=excluded.media_json,
                  text_de=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.text_de ELSE '' END,
                  translation_status=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.translation_status ELSE 'pending' END,
                  translation_next_at=CASE WHEN posts.text_hash=excluded.text_hash THEN posts.translation_next_at ELSE 0 END,
                  text=excluded.text,text_hash=excluded.text_hash,link_only=excluded.link_only''',
                  ('x:'+str(source['id'])+':'+v['external_id'],source['id'],v['external_id'],v['author'],v['text'],v['url'],v['published_at'],json.dumps(v.get('media',[])),now,digest,int(not has_story_text(v['text']))))
                seen,favorite=newsroom.preserve_discovery_state(c,'x',v['external_id'])
                c.execute('UPDATE posts SET seen=max(seen,?),favorite=max(favorite,?) WHERE id=?',
                  (seen,favorite,'x:'+str(source['id'])+':'+v['external_id']))
                continue
            ident=source['platform']+':'+v['external_id']
            eligible=int(v['format'] not in first_kinds or v['external_id'] in initial_selection[v['format']])
            c.execute('''INSERT INTO videos(id,source_id,external_id,platform,format,title,url,thumbnail,published_at,duration,discovered_at,feed_eligible)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              format=excluded.format,title=excluded.title,url=excluded.url,thumbnail=excluded.thumbnail,
              published_at=COALESCE(excluded.published_at,videos.published_at),duration=excluded.duration''',
              (ident,source['id'],v['external_id'],source['platform'],v['format'],v['title'],v['url'],v.get('thumbnail',''),v.get('published_at'),v.get('duration',''),now,eligible))
            if v['format'] in first_kinds:c.execute('UPDATE videos SET feed_eligible=? WHERE id=?',(eligible,ident))
            seen,favorite=newsroom.preserve_discovery_state(c,source['platform'],v['external_id'])
            c.execute('UPDATE videos SET seen=max(seen,?),favorite=max(favorite,?) WHERE id=?',(seen,favorite,ident))
        for kind in first_kinds:c.execute('INSERT OR IGNORE INTO feed_windows VALUES(?,?,?)',(source['id'],kind,now))
        c.execute('''UPDATE sources SET title=?,channel_id=COALESCE(?,channel_id),status=?,message=?,checked_at=?,success_at=?,next_at=?,failures=0 WHERE id=?''',
          (meta.get('title') or source['title'],meta.get('channel_id'),'partial' if warnings else 'ok',' '.join(warnings)[:1200],now,now,time.time()+interval,source['id']))

def refresh_one(source):
    try:
        videos,meta,warnings=collect(source);save_success(source,videos,meta,warnings)
        return True
    except Exception as e:
        with db() as c:
            c.execute("UPDATE sources SET status='error',message=?,checked_at=?,failures=failures+1,next_at=? WHERE id=?",
              (str(e)[:1200],utc(),time.time()+min(21600,900*2**min(source['failures'],4)),source['id']))
        return False

def refresh(force=False):
    global RUNNING
    with JOB_LOCK:
        if RUNNING:return False
        RUNNING=True
    def job():
        global RUNNING
        try:
            with db() as c:
                sources=[dict(s) for s in c.execute('SELECT * FROM sources WHERE enabled=1'+('' if force else ' AND next_at<=?'),() if force else (time.time(),))]
                run_id=c.execute('INSERT INTO runs(started_at) VALUES(?)',(utc(),)).lastrowid
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: successes=list(pool.map(refresh_one,sources))
            with db() as c:c.execute('UPDATE runs SET finished_at=?,successful=?,failed=? WHERE id=?',(utc(),sum(successes),len(successes)-sum(successes),run_id))
        finally:
            with JOB_LOCK:RUNNING=False
    threading.Thread(target=job,daemon=True,name='collector').start()
    return True

def scheduler():
    while True:
        refresh();newsroom.tick();time.sleep(60)

def sources():
    with db() as c:return [dict(s) for s in c.execute('''SELECT s.*,
      (SELECT count(*) FROM videos v WHERE v.source_id=s.id AND s.delivery!='news' AND v.feed_eligible=1 AND v.seen=0 AND (s.mode='both' OR s.mode=v.format)) AS video_count,
      (SELECT count(*) FROM posts p WHERE p.source_id=s.id AND p.link_only=0) AS post_count FROM sources s ORDER BY s.id''')]


def has_story_text(text):
    text=re.sub(r'(?:https?://|www\.|pic\.twitter\.com/|t\.co/)\S+','',text,flags=re.I).strip()
    text=re.sub(r'(?i)^(?:source|quelle|link|video|thread)(?:\s*\d+)?[\s:.,!\-–—]*$','',text).strip()
    return any(ch.isalpha() for ch in text)


def claim_translations(limit=4):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=[dict(r) for r in c.execute('''SELECT p.id,p.text,p.text_hash FROM posts p JOIN sources s ON s.id=p.source_id
          WHERE s.enabled=1 AND p.link_only=0 AND p.translation_status!='ready' AND p.translation_next_at<=?
          ORDER BY p.published_at DESC LIMIT ?''',(time.time(),max(1,min(8,int(limit)))))]
        for row in rows:c.execute("UPDATE posts SET translation_status='working',translation_next_at=? WHERE id=?",(time.time()+240,row['id']))
        rows+=newsroom.claim_discovery_translations(c,max(1,min(8,int(limit)))-len(rows))
    return rows


def complete_translations(results):
    if not isinstance(results,list) or len(results)>8:raise ValueError('Ungültige Übersetzungsliste.')
    saved=0
    with db() as c:
        for item in results:
            if not isinstance(item,dict):raise ValueError('Ungültige Übersetzung.')
            ident=str(item.get('id',''));digest=str(item.get('text_hash',''))
            text=item.get('text_de','')
            if not isinstance(text,str) or len(text)>100000:raise ValueError('Übersetzung zu groß.')
            if ident.startswith('discovery:'):
                saved+=newsroom.complete_discovery_translation(c,ident.split(':',1)[1],digest,text);continue
            if text.strip():
                saved+=c.execute("UPDATE posts SET text_de=?,translation_status='ready',translation_next_at=0 WHERE id=? AND text_hash=?",(text.strip(),ident,digest)).rowcount
            else:c.execute("UPDATE posts SET translation_status='error',translation_attempts=translation_attempts+1,translation_next_at=? WHERE id=? AND text_hash=?",(time.time()+900,ident,digest))
    return saved


def posts(source_id=0,unseen=False):
    query='''SELECT p.*,s.title AS creator,s.handle FROM posts p JOIN sources s ON s.id=p.source_id WHERE s.enabled=1 AND p.link_only=0'''
    params=[]
    if source_id:query+=' AND p.source_id=?';params.append(int(source_id))
    if unseen:query+=' AND p.seen=0'
    query+=' ORDER BY p.published_at DESC,p.external_id DESC LIMIT 300'
    with db() as c:rows=[dict(p) for p in c.execute(query,params)]
    for p in rows:
        p['media']=json.loads(p.pop('media_json'))
        if not AI_ENABLED and p.get('translation_status')!='ready':p['translation_status']='original'
    return rows

def feed(kind,platform='',unseen=True):
    if kind not in ('long','short'):raise ValueError('Unbekanntes Videoformat.')
    query='''SELECT v.*,s.title AS creator,s.handle FROM videos v JOIN sources s ON v.source_id=s.id
      WHERE s.enabled=1 AND s.delivery!='news' AND v.feed_eligible=1 AND v.format=? AND (s.mode='both' OR s.mode=v.format)'''
    params=[kind]
    if platform in ('youtube','tiktok'):query+=' AND v.platform=?';params.append(platform)
    if unseen:query+=' AND v.seen=0'
    query+=' ORDER BY (v.published_at IS NULL),v.published_at DESC,v.discovered_at DESC,v.rowid ASC'
    with db() as c:rows=[dict(v) for v in c.execute(query,params)]
    queues={}
    for video in rows:queues.setdefault(video['source_id'],deque()).append(video)
    mixed=[]
    while queues:
        for source_id in list(queues):
            mixed.append(queues[source_id].popleft())
            if not queues[source_id]:del queues[source_id]
    discoveries=newsroom.discovery_feed(kind,platform,unseen)
    known={v['id'] for v in mixed};discoveries=[v for v in discoveries if v['id'] not in known]
    for index,video in enumerate(discoveries):mixed.insert(min(len(mixed),3+index*4),video)
    return mixed

def normalize_source(raw,mode,platform=''):
    if platform=='rss':
        newsroom.public_url(raw.strip())
        return {'platform':'rss','handle':raw.strip(),'channel_id':None,'mode':'posts'}
    if mode not in ('long','short','both'):raise ValueError('Wähle lange Videos, Shorts oder beides.')
    p=urllib.parse.urlsplit(raw.strip())
    if p.scheme!='https' or p.username or p.password or p.port or p.query or p.fragment:raise ValueError('Bitte einen HTTPS-Kanallink ohne Suchparameter einfügen.')
    host=p.hostname;path=p.path.rstrip('/')
    if host in ('youtube.com','www.youtube.com'):
        m=re.fullmatch(r'/@([\w.\-\u0080-\uffff]{2,80})(?:/(?:videos|shorts|featured))?',path)
        if m:return {'platform':'youtube','handle':m[1],'channel_id':None,'mode':mode}
        m=re.fullmatch(r'/channel/(UC[\w-]{22})',path)
        if m:return {'platform':'youtube','handle':m[1],'channel_id':m[1],'mode':mode}
    if host in ('tiktok.com','www.tiktok.com'):
        m=re.fullmatch(r'/@([\w.]{2,24})',path)
        if m:return {'platform':'tiktok','handle':m[1],'channel_id':None,'mode':'short'}
    if host in ('x.com','www.x.com','twitter.com','www.twitter.com'):
        m=re.fullmatch(r'/([A-Za-z0-9_]{1,15})',path)
        if m and m[1].lower() not in {'home','explore','search','settings','messages','notifications','i','intent','share','login','logout'}:
            return {'platform':'x','handle':m[1].lower(),'channel_id':None,'mode':'posts'}
    raise ValueError('Bitte den Profil-Link von YouTube, TikTok oder X einfügen, für RSS den Quellentyp rss wählen.')

def news(source_id=0,unseen=False):
    rows=posts(source_id,unseen)+newsroom.summary_news(source_id,unseen)
    if not source_id:rows+=newsroom.discovery_news(unseen)
    for row in rows:
        row.setdefault('basis','RSS-/Atom-Feedtext (kann ein Auszug sein)' if row.get('kind')=='rss' else 'Originalbeitrag')
        if not AI_ENABLED and row.get('translation_status')!='ready':row['translation_status']='original'
    rows.sort(key=lambda r:r.get('published_at') or '',reverse=True)
    # One article URL once, including when syndicated by several feeds.
    result=[];seen=set()
    for row in rows:
        key=newsroom.canonical(row['url']) or row['id']
        if key in seen:continue
        seen.add(key);result.append(row)
    regular=[p for p in result if not p.get('is_discovery')]
    for index,post in enumerate(p for p in result if p.get('is_discovery')):regular.insert(min(len(regular),3+index*4),post)
    return regular[:300]

class Handler(BaseHTTPRequestHandler):
    server_version='KISocialMedia/'+VERSION
    def log_message(self,*args):pass  # Never log tokens, pairing codes, or personal query strings.
    def send(self,status,value,ctype='application/json; charset=utf-8'):
        raw=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value.encode()
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin');self.end_headers();self.wfile.write(raw)
    def path_parts(self):
        p=urllib.parse.urlsplit(self.path);path=p.path
        if path.startswith('/cody-social/'):path=path[len('/cody-social'):]
        return path,urllib.parse.parse_qs(p.query)
    def authenticated(self):
        return bool(TOKEN) and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN)
    def translator_authenticated(self):
        return len(TRANSLATOR_TOKEN)>=32 and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TRANSLATOR_TOKEN)
    def speech_authenticated(self):
        return len(SPEECH_TOKEN)>=32 and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+SPEECH_TOKEN)
    def do_GET(self):
        path,q=self.path_parts()
        if path=='/health':return self.send(200,{'service':'cody-social','version':VERSION})
        m=re.fullmatch(r'/player/(youtube|tiktok)/([\w-]{11}|\d{15,25})',path)
        if m:
            platform,ident=m.groups()
            if platform=='youtube' and not re.fullmatch(r'[\w-]{11}',ident):return self.send(400,{'error':'Ungültiges Video.'})
            if platform=='tiktok' and not ident.isdigit():return self.send(400,{'error':'Ungültiges Video.'})
            return self.send(200,player_html(platform,ident),'text/html; charset=utf-8')
        if not self.authenticated():return self.send(401,{'error':'Bitte diese App mit deinem Server verbinden.'})
        if path=='/api/sources':return self.send(200,{'sources':sources(),'refreshing':RUNNING})
        if path=='/api/capabilities':return self.send(200,{'ai_enabled':AI_ENABLED,'version':VERSION,'news_endpoint':'/api/news','source_platforms':['youtube','tiktok','x','rss'],
          'delivery':{'youtube':['videos','news','both'],'tiktok':['videos'],'x':['news'],'rss':['news']},
          'discovery_platforms':['youtube','x','tiktok'],'max_discovery_runs_per_day':2,'max_suggestions_per_run':3,'speech':newsroom.speech_status()})
        if path=='/api/discovery':return self.send(200,newsroom.discovery_status())
        if path=='/api/suggestions':return self.send(200,{'suggestions':newsroom.suggestions()})
        if path=='/api/summaries':return self.send(200,{'summaries':newsroom.summary_status()})
        if path=='/api/news':
            try:return self.send(200,{'posts':news(int(q.get('source_id',['0'])[0]),q.get('unseen',['0'])[0]=='1')})
            except ValueError:return self.send(400,{'error':'Ungültige Quellen-Auswahl.'})
        if path=='/api/posts':
            try:return self.send(200,{'posts':posts(int(q.get('source_id',['0'])[0]),q.get('unseen',['0'])[0]=='1'),'refreshing':RUNNING})
            except ValueError:return self.send(400,{'error':'Ungültige Creator-Auswahl.'})
        if path=='/api/feed':
            try:return self.send(200,{'videos':feed(q.get('format',['long'])[0],q.get('platform',[''])[0],q.get('unseen',['1'])[0]=='1'),'refreshing':RUNNING})
            except ValueError as e:return self.send(400,{'error':str(e)})
        return self.send(404,{'error':'Nicht gefunden.'})
    def do_POST(self):
        global LAST_MANUAL
        path,_=self.path_parts()
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>(500000 if path.startswith('/internal/') else 16384):return self.send(413,{'error':'Anfrage zu groß.'})
            body=json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body,dict):raise ValueError('Ungültige Anfrage.')
            if path.startswith('/internal/speech/'):
                if not self.speech_authenticated():return self.send(401,{'error':'Whisper-Dienst nicht angemeldet.'})
                if path=='/internal/speech/status':newsroom.set_speech_status(body);return self.send(200,{'ok':True})
                if path=='/internal/speech/claim':return self.send(200,{'jobs':newsroom.claim_speech()})
                if path=='/internal/speech/result':return self.send(200,{'saved':newsroom.complete_speech(body)})
                return self.send(404,{'error':'Nicht gefunden.'})
            if path.startswith('/internal/editorial/'):
                if not self.translator_authenticated():return self.send(401,{'error':'KI-Dienst nicht angemeldet.'})
                if path=='/internal/editorial/claim':return self.send(200,{'jobs':newsroom.claim_jobs()})
                if path=='/internal/editorial/result':return self.send(200,{'saved':newsroom.complete_job(body)})
                return self.send(404,{'error':'Nicht gefunden.'})
            if path.startswith('/internal/translation/'):
                if not self.translator_authenticated():return self.send(401,{'error':'Übersetzer nicht angemeldet.'})
                if path=='/internal/translation/claim':return self.send(200,{'jobs':claim_translations(body.get('limit',4))})
                if path=='/internal/translation/result':return self.send(200,{'saved':complete_translations(body.get('results',[]))})
                return self.send(404,{'error':'Nicht gefunden.'})
            if path=='/api/pair':
                peer=self.client_address[0];recent=[t for t in PAIR_ATTEMPTS.get(peer,[]) if t>time.time()-600]
                PAIR_ATTEMPTS[peer]=recent+[time.time()]
                if len(recent)>=10:return self.send(429,{'error':'Zu viele Versuche. Bitte zehn Minuten warten.'})
                pair,expires=pairing()
                if not pair or time.time()>expires or not hmac.compare_digest(str(body.get('code','')),pair):return self.send(403,{'error':'Verbindungscode ungültig oder abgelaufen.'})
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    digest=hashlib.sha256(pair.encode()).hexdigest()
                    if c.execute('SELECT 1 FROM meta WHERE key=?',('pair:'+digest,)).fetchone():return self.send(403,{'error':'Dieser Verbindungscode wurde schon verwendet.'})
                    c.execute('INSERT INTO meta VALUES(?,?)',('pair:'+digest,utc()))
                return self.send(200,{'token':TOKEN,'name':'KI Social Media'})
            if not self.authenticated():return self.send(401,{'error':'Bitte zuerst mit dem Pi verbinden.'})
            if path=='/api/discovery':
                if body.get('enabled') and not AI_ENABLED:raise ValueError('Entdecker benötigt einen konfigurierten KI-Anbieter (AI_ENABLED=true).')
                return self.send(200,{'settings':newsroom.set_settings(body)})
            if path=='/api/creator/block':return self.send(200,newsroom.creator_block(body))
            if path=='/api/suggestion':
                newsroom.feedback(body)
                if body.get('action')=='subscribe':refresh()
                return self.send(200,{'ok':True})
            if path=='/api/summary':
                if not AI_ENABLED:raise ValueError('Zusammenfassungen benötigen einen konfigurierten KI-Anbieter.')
                newsroom.queue_summary(str(body.get('video_id','')));newsroom.tick()
                return self.send(202,{'ok':True})
            if path=='/api/refresh':
                if time.time()-LAST_MANUAL<60:return self.send(429,{'error':'Die letzte Aktualisierung läuft noch oder liegt weniger als eine Minute zurück.'})
                LAST_MANUAL=time.time();started=refresh(True)
                return self.send(202,{'started':started,'refreshing':True})
            if path=='/api/source':
                ident=body.get('id')
                with db() as c:
                    if body.get('delete'):
                        c.execute('DELETE FROM sources WHERE id=?',(int(ident),))
                    elif ident:
                        row=c.execute('SELECT * FROM sources WHERE id=?',(int(ident),)).fetchone()
                        if not row:raise ValueError('Creator nicht gefunden.')
                        mode=body.get('mode',row['mode'])
                        if mode not in ('long','short','both','posts'):raise ValueError('Ungültige Auswahl.')
                        if row['platform']=='youtube' and mode=='posts':raise ValueError('Ungültiges YouTube-Format.')
                        if row['platform']=='tiktok':mode='short'
                        if row['platform'] in ('x','rss'):mode='posts'
                        delivery=body.get('delivery',row['delivery'])
                        if delivery not in ('videos','news','both'):raise ValueError('Ungültige News-Auswahl.')
                        if row['platform'] in ('x','rss'):delivery='news'
                        if row['platform']=='tiktok' and delivery!='videos':raise ValueError('TikTok-Zusammenfassungen benötigen noch einen Transkriptzugang.')
                        c.execute('UPDATE sources SET mode=?,delivery=?,enabled=?,next_at=0 WHERE id=?',(mode,delivery,int(bool(body.get('enabled',row['enabled']))),ident))
                    else:
                        s=normalize_source(str(body.get('url','')),body.get('mode','both'),str(body.get('platform','')))
                        delivery=body.get('delivery','news' if s['platform'] in ('x','rss') else 'videos')
                        if delivery not in ('videos','news','both'):raise ValueError('Ungültige News-Auswahl.')
                        if s['platform'] in ('x','rss'):delivery='news'
                        if s['platform']=='tiktok' and delivery!='videos':raise ValueError('TikTok-Zusammenfassungen benötigen noch einen Transkriptzugang.')
                        c.execute('INSERT INTO sources(platform,handle,title,channel_id,mode,delivery) VALUES(?,?,?,?,?,?) ON CONFLICT(platform,handle) DO UPDATE SET enabled=1,mode=excluded.mode,delivery=excluded.delivery,next_at=0',
                                  (s['platform'],s['handle'],s['handle'],s['channel_id'],s['mode'],delivery))
                if not body.get('delete'):refresh()
                return self.send(200,{'ok':True})
            if path=='/api/video':
                subscribed=None
                with db() as c:
                    for key in ('seen','favorite'):
                        if key in body:
                            c.execute('UPDATE videos SET '+key+'=? WHERE id=?',(int(bool(body[key])),str(body.get('id',''))))
                            newsroom.mark_discovery(c,str(body.get('id','')),key,int(bool(body[key])))
                    if body.get('favorite') is True:subscribed=newsroom.favorite_creator(c,str(body.get('id','')))
                if subscribed:refresh()
                return self.send(200,{'ok':True,'subscribed_creator':subscribed})
            if path=='/api/seen':
                ids=body.get('ids',[])
                if not isinstance(ids,list) or len(ids)>500 or any(not isinstance(i,str) or len(i)>100 for i in ids):raise ValueError('Ungültige Videoliste.')
                with db() as c:
                    c.executemany('UPDATE videos SET seen=1 WHERE id=?',[(i,) for i in ids])
                    for ident in ids:newsroom.mark_discovery(c,ident,'seen',1)
                return self.send(200,{'ok':True,'ids':ids})
            if path=='/api/post':
                ident=str(body.get('id',''))
                subscribed=None
                with db() as c:
                    for key in ('seen','favorite'):
                        if key in body:
                            newsroom.mark_discovery(c,ident,key,int(bool(body[key])))
                            if ident.startswith('summary:'):c.execute('UPDATE videos SET '+key+'=? WHERE id=?',(int(bool(body[key])),ident[len('summary:'):]))
                            else:
                                # Apply RSS duplicate state to the same canonical URL across feeds.
                                row=c.execute('SELECT url,kind FROM posts WHERE id=?',(ident,)).fetchone()
                                if row and row['kind']=='rss':
                                    canonical=newsroom.canonical(row['url'])
                                    ids=[(int(bool(body[key])),r['id']) for r in c.execute("SELECT id,url FROM posts WHERE kind='rss'") if newsroom.canonical(r['url'])==canonical]
                                    c.executemany('UPDATE posts SET '+key+'=? WHERE id=?',ids)
                                else:c.execute('UPDATE posts SET '+key+'=? WHERE id=?',(int(bool(body[key])),ident))
                    if body.get('favorite') is True:subscribed=newsroom.favorite_creator(c,ident)
                if subscribed:refresh()
                return self.send(200,{'ok':True,'subscribed_creator':subscribed})
            return self.send(404,{'error':'Nicht gefunden.'})
        except (ValueError,TypeError,sqlite3.IntegrityError) as e:return self.send(400,{'error':str(e)[:300]})
        except Exception:return self.send(500,{'error':'Der Server konnte die Anfrage gerade nicht verarbeiten.'})

def player_html(platform,ident):
    # The native message listener accepts only this exact HTTPS origin and the main frame.
    common='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><style>html,body{margin:0;width:100vw;height:100vh;background:#030912;color:white;overflow:hidden}iframe,#player{position:fixed;inset:0;display:block;border:0;width:100vw!important;height:100vh!important}#notice{position:absolute;bottom:4px;left:6px;pointer-events:none;font:12px sans-serif}</style></head><body>'''
    emit='''function emit(x){if(window.CodyPlayback)CodyPlayback.postMessage(JSON.stringify(x));}
    function fitPlayer(){const f=document.getElementById('player');if(!f)return;f.style.setProperty('position','fixed','important');f.style.setProperty('top','0','important');f.style.setProperty('left','0','important');f.style.setProperty('display','block','important');f.style.setProperty('width',innerWidth+'px','important');f.style.setProperty('height',innerHeight+'px','important');}
    fitPlayer();new MutationObserver(fitPlayer).observe(document.body,{childList:true});window.addEventListener('resize',fitPlayer);setTimeout(fitPlayer,100);setTimeout(fitPlayer,1000);
    window.codyPause=function(){try{if(typeof p!=='undefined'&&p&&typeof p.pauseVideo==='function')p.pauseVideo();const frame=document.getElementById('player');if(frame&&frame.tagName==='IFRAME'&&new URL(frame.src).hostname==='www.tiktok.com')frame.contentWindow.postMessage({'x-tiktok-player':true,type:'pause'},'https://www.tiktok.com');}catch(e){}};
    document.addEventListener('visibilitychange',()=>{if(document.hidden)codyPause();});window.addEventListener('pagehide',codyPause);
    setTimeout(()=>{const f=document.getElementById('player'),r=f.getBoundingClientRect();emit({type:'layout',seconds:r.width,state:Math.round(r.height),code:innerHeight});},3500);'''
    if platform=='youtube':
        youtube_script='''let p,clearingCaptions=false;
        function captionsOff(){
          if(!p||clearingCaptions)return;
          clearingCaptions=true;
          try{
            if(typeof p.unloadModule==='function')p.unloadModule('captions');
            else if(typeof p.setOption==='function')p.setOption('captions','track',{});
            emit({type:'captions-off',code:typeof p.unloadModule==='function'?1:0,platform:'youtube'});
          }catch(e){}finally{setTimeout(()=>clearingCaptions=false,100);}
        }
        function onYouTubeIframeAPIReady(){
          p=new YT.Player('player',{
            videoId:'__VIDEO_ID__',
            playerVars:{autoplay:1,playsinline:1,controls:1,rel:0,cc_load_policy:0,origin:location.origin},
            events:{
              onReady:()=>{captionsOff();setTimeout(captionsOff,500);fitPlayer();emit({type:'ready',platform:'youtube'});},
              onApiChange:captionsOff,
              onStateChange:e=>{if(e.data===1&&document.hidden)codyPause();emit({type:'state',state:e.data,platform:'youtube'});},
              onError:e=>emit({type:'error',code:e.data,platform:'youtube'}),
              onAutoplayBlocked:()=>emit({type:'blocked',platform:'youtube'})
            }
          });
          setInterval(()=>{if(p&&p.getCurrentTime)emit({type:'time',seconds:p.getCurrentTime(),duration:p.getDuration(),platform:'youtube'});},1000);
        }'''
        return common+'<div id="player"></div><script>'+emit+youtube_script.replace('__VIDEO_ID__',ident)+'</script><script src="https://www.youtube.com/iframe_api"></script></body></html>'
    return common+'''<iframe id="player" src="https://www.tiktok.com/player/v1/'''+ident+'''?autoplay=1&controls=1&description=0&rel=0" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe><script>'''+emit+'''const f=document.getElementById('player');window.addEventListener('message',e=>{if(e.origin!=='https://www.tiktok.com'||e.source!==f.contentWindow||!e.data||e.data['x-tiktok-player']!==true)return;const m=e.data;if(m.type==='onPlayerReady')emit({type:'ready',platform:'tiktok'});if(m.type==='onStateChange')emit({type:'state',state:m.value,platform:'tiktok'});if(m.type==='onCurrentTime')emit({type:'time',seconds:m.value.currentTime,duration:m.value.duration,platform:'tiktok'});if(m.type==='onPlayerError')emit({type:'error',code:m.value.errorCode,platform:'tiktok'});});</script></body></html>'''

def main():
    if len(TOKEN)<32:raise SystemExit('CODY_API_TOKEN fehlt oder ist zu kurz.')
    initialize();threading.Thread(target=scheduler,daemon=True).start()
    server=ThreadingHTTPServer((os.environ.get('CODY_HOST','127.0.0.1'),int(os.environ.get('CODY_PORT','9131'))),Handler)
    print('KI Social Media '+VERSION+' bereit.',flush=True);server.serve_forever()

if __name__=='__main__':main()
