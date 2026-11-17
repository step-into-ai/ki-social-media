"""Fresh-install CI smoke check. Use ONLY against this checkout's new test instance."""
import json
import pathlib
import subprocess
import time
import urllib.error
import urllib.request

from manage import load_env
import os

ROOT = pathlib.Path(__file__).resolve().parents[1]


def container(*args):
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'backend', *args], cwd=ROOT,
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Container check failed; inspect service status without publishing credentials.')
    return result.stdout


def main():
    load_env()
    config=json.loads(subprocess.check_output(['docker','compose','--profile','*','config','--format','json'],cwd=ROOT))
    assert 'CODY_API_TOKEN' not in config['services']['ai']['environment']
    assert 'CODY_API_TOKEN' not in config['services']['speech']['environment']
    assert 'AI_API_KEY' not in config['services']['backend']['environment']
    assert 'SPEECH_API_KEY' not in config['services']['backend']['environment']
    base = 'http://127.0.0.1:' + os.environ.get('CODY_PORT', '9131')
    token = os.environ['CODY_API_TOKEN']
    def request(path, body=None, credential=None):
        headers = {'Content-Type': 'application/json'}
        if credential:headers['Authorization'] = 'Bearer ' + credential
        req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None, headers)
        with urllib.request.urlopen(req, timeout=10) as response:return json.load(response)
    for attempt in range(60):
        try:request('/health');break
        except (OSError, ValueError):time.sleep(1)
    else:raise RuntimeError('Health check did not become ready.')
    for path in ('/api/sources', '/api/feed', '/api/news', '/api/capabilities'):
        try:request(path)
        except urllib.error.HTTPError as error:assert error.code == 401
        else:raise AssertionError('Personal endpoint accepted an unauthenticated request.')
        request(path, credential=token)
    assert request('/api/sources', credential=token)['sources'] == []
    assert request('/api/capabilities', credential=token)['ai_enabled'] is False
    container('python', 'tools/manage.py', 'pair', '--quiet')
    pairing = json.loads(container('python', '-c', "import pathlib; print(pathlib.Path('/data/pairing.json').read_text())"))
    assert request('/api/pair', {'code': pairing['code']})['token'] == token
    try:request('/api/pair', {'code': pairing['code']})
    except urllib.error.HTTPError as error:assert error.code == 403
    else:raise AssertionError('Pairing code was reusable.')
    container('python', 'tools/manage.py', 'pair', '--quiet')
    pairing = json.loads(container('python', '-c', "import pathlib; print(pathlib.Path('/data/pairing.json').read_text())"))
    assert request('/api/pair', {'code': pairing['code']})['token'] == token
    container('python', 'tools/manage.py', 'backup')
    subprocess.run(['docker', 'compose', 'restart', 'backend'], cwd=ROOT, check=True, capture_output=True, timeout=90)
    for attempt in range(60):
        try:request('/api/sources', credential=token);break
        except OSError:time.sleep(1)
    else:raise RuntimeError('Instance did not recover after restart.')
    print('Fresh container: health, empty private library, auth, pairing, rotation, backup and restart passed.')


if __name__ == '__main__':main()
