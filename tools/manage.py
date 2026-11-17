"""Local instance management. Never reads another project's settings or credentials."""
import argparse
import contextlib
import datetime
import json
import os
import pathlib
import runpy
import secrets
import sqlite3
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


def data_dir():
    return pathlib.Path(os.environ.get('CODY_DATA', str(ROOT / 'data')))


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    path.chmod(0o600)


def init(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use your own HTTPS server URL without credentials or query strings.')
    path = ROOT / '.env'
    if path.exists():
        raise ValueError('.env already exists; credentials are preserved. Edit it instead of initializing again.')
    text = (ROOT / '.env.example').read_text(encoding='utf-8')
    for name in ('CODY_API_TOKEN', 'CODY_TRANSLATOR_TOKEN', 'CODY_SPEECH_TOKEN'):
        text = text.replace(name + '=\n', name + '=' + secrets.token_urlsafe(48) + '\n')
    text = text.replace('PUBLIC_URL=https://YOUR-SERVER', 'PUBLIC_URL=' + url.rstrip('/'))
    private_write(path, text)
    data_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    print('Initialized private .env. No accounts, sources or provider credentials were imported.')


def pair(show=True):
    code = secrets.token_urlsafe(24)
    expires = time.time() + 1800
    private_write(data_dir() / 'pairing.json', json.dumps({'code': code, 'expires': expires}))
    if show:
        base = os.environ.get('PUBLIC_URL', '').rstrip('/')
        print('Server: ' + base)
        print('One-use code (valid for 30 minutes): ' + code)
        print('Open on Android: kisocial://pair?' + urllib.parse.urlencode({'server': base, 'code': code}))
    return code


def backup():
    database = data_dir() / 'cody-social.db'
    if not database.is_file():
        raise ValueError('Database does not exist yet.')
    folder = data_dir() / 'backups'
    folder.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = folder / ('ki-social-' + stamp + '.db')
    with contextlib.closing(sqlite3.connect(database)) as source, contextlib.closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity check failed.')
    target.chmod(0o600)
    print('Created verified SQLite backup: ' + target.name)


def restore(path, stopped):
    if not stopped:
        raise ValueError('Stop backend and workers first, then pass --service-stopped.')
    candidate = pathlib.Path(path).resolve(strict=True)
    folder = (data_dir() / 'backups').resolve()
    if candidate.parent != folder or candidate.suffix != '.db':
        raise ValueError('Select a .db snapshot inside this instance\'s data/backups directory.')
    with contextlib.closing(sqlite3.connect(candidate)) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Snapshot integrity check failed.')
        if (data_dir() / 'cody-social.db').exists():
            backup()
        with contextlib.closing(sqlite3.connect(data_dir() / 'cody-social.db')) as destination:
            source.backup(destination)
    print('Restored verified snapshot. Restart the instance.')


def doctor():
    token = os.environ.get('CODY_API_TOKEN', '')
    if len(token) < 32:
        raise ValueError('Missing private API credential. Run init first.')
    base = 'http://127.0.0.1:' + os.environ.get('CODY_PORT', '9131')
    for path, authorization in [('/health', False), ('/api/sources', True), ('/api/capabilities', True)]:
        request = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token} if authorization else {})
        with urllib.request.urlopen(request, timeout=10) as response:
            json.load(response)
        print(path + ': OK')
    try:
        urllib.request.urlopen(base + '/api/sources', timeout=10)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            print('Unauthenticated library access: rejected (401)')
            return
    raise ValueError('Unauthenticated library access was not rejected.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('init');command.add_argument('--url', required=True)
    command = sub.add_parser('pair');command.add_argument('--quiet', action='store_true')
    sub.add_parser('prepare-data')
    sub.add_parser('backup')
    command = sub.add_parser('restore');command.add_argument('snapshot');command.add_argument('--service-stopped', action='store_true')
    sub.add_parser('doctor')
    sub.add_parser('serve')
    args = parser.parse_args()
    load_env()
    if args.command == 'init':init(args.url)
    elif args.command == 'pair':pair(not args.quiet)
    elif args.command == 'backup':backup()
    elif args.command == 'restore':restore(args.snapshot, args.service_stopped)
    elif args.command == 'doctor':doctor()
    elif args.command == 'prepare-data':
        folder = data_dir().resolve()
        if folder != pathlib.Path('/data') or not hasattr(os, 'geteuid') or os.geteuid() != 0:
            raise ValueError('This helper is only for the container\'s /data mount as root.')
        if folder.is_symlink():raise ValueError('Data must not be a symlink.')
        folder.mkdir(exist_ok=True)
        os.chown(folder,0,0);folder.chmod(0o700)
        try:
            model_dir=folder/'tiktok-language'
            if model_dir.is_symlink():raise ValueError('Model directory must not be a symlink.')
            if not model_dir.exists():
                model_dir.mkdir(mode=0o700);os.chown(model_dir,10001,10001)
        finally:os.chown(folder,10001,10001)
        print('Prepared the dedicated data mount for UID 10001.')
    elif args.command == 'serve':
        sys.path.insert(0,str(ROOT/'collector'))
        runpy.run_path(str(ROOT/'collector/service.py'),run_name='__main__')


if __name__ == '__main__':
    try:main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
