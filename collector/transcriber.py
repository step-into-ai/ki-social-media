"""Optional audio transcription through a compatible API or a local whisper.cpp CLI."""
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from provider import endpoint

BASE = os.environ.get('CODY_SPEECH_API', 'http://127.0.0.1:9131')
TOKEN = os.environ.get('CODY_SPEECH_TOKEN', '')


def api(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(),
        {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def available():
    provider = os.environ.get('SPEECH_PROVIDER', 'disabled')
    if provider == 'local':
        return bool(shutil.which(os.environ.get('SPEECH_LOCAL_BIN', 'whisper-cli'))
                    and pathlib.Path(os.environ.get('SPEECH_LOCAL_MODEL', '/nonexistent')).is_file())
    return provider == 'compatible' and bool(os.environ.get('SPEECH_BASE_URL') and os.environ.get('SPEECH_MODEL'))


def transcribe_file(audio):
    if os.environ.get('SPEECH_PROVIDER') == 'local':
        wav = audio.with_suffix('.wav')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(audio), '-ac', '1', '-ar', '16000', str(wav)],
                       check=True, capture_output=True, timeout=300)
        output = audio.parent / 'transcript'
        result = subprocess.run([os.environ.get('SPEECH_LOCAL_BIN', 'whisper-cli'), '-m', os.environ['SPEECH_LOCAL_MODEL'],
            '-f', str(wav), '-t', os.environ.get('SPEECH_LOCAL_THREADS', '2'), '-l', 'auto', '-otxt', '-of', str(output)],
            capture_output=True, timeout=3600)
        if result.returncode:
            raise ValueError('Local speech recognition failed.')
        return output.with_suffix('.txt').read_text(encoding='utf-8').strip()
    if audio.stat().st_size > 24_000_000:
        raise ValueError('Audio exceeds the configured API upload limit (24 MB).')
    boundary = 'KISocial' + secrets.token_hex(16)
    parts = []
    for name, value in [('model', os.environ['SPEECH_MODEL']), ('response_format', 'json')]:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
    parts += [(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.m4a"\r\nContent-Type: audio/mp4\r\n\r\n').encode(),
              audio.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()]
    headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary}
    if os.environ.get('SPEECH_API_KEY'):
        headers['Authorization'] = 'Bearer ' + os.environ['SPEECH_API_KEY']
    url = endpoint(os.environ['SPEECH_BASE_URL'], 'audio/transcriptions', os.environ.get('SPEECH_ALLOW_HTTP') == 'true')
    request = urllib.request.Request(url, b''.join(parts), headers)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Response too large.')
        text = json.loads(raw).get('text', '')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty transcript.')
        return text.strip()
    except Exception:
        raise ValueError('The configured speech endpoint did not return a transcript.') from None


def transcribe_audio(url):
    if not available():
        raise ValueError('Speech recognition is not configured.')
    if not re.fullmatch(r'https://www.youtube.com/watch\?v=[\w-]{11}', url):
        raise ValueError('Only the queued public YouTube video is accepted.')
    with tempfile.TemporaryDirectory(prefix='ki-social-speech-') as directory:
        target = pathlib.Path(directory)
        result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-cache-dir', '--no-playlist', '--no-progress',
            '--no-warnings', '--socket-timeout', '25', '--retries', '0', '--fragment-retries', '0', '--max-filesize', '128M',
            '-f', 'bestaudio', '-x', '--audio-format', 'm4a', '-o', str(target / 'source.%(ext)s'), '--', url],
            capture_output=True, timeout=1200)
        source = target / 'source.m4a'
        if result.returncode or not source.is_file() or source.stat().st_size > 128 * 1024 * 1024:
            raise ValueError('Public audio is currently unavailable.')
        audio = target / 'audio.m4a'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-vn', '-ac', '1', '-c:a', 'aac',
            '-b:a', '32k', '-fs', '24000001', str(audio)], check=True, capture_output=True, timeout=600)
        # Reject files at the cap; never summarize a truncated transcript as a complete video.
        if audio.stat().st_size >= 24_000_000:
            raise ValueError('Audio exceeds the full-video transcription limit.')
        return transcribe_file(audio)


def cycle():
    ready = available()
    provider = os.environ.get('SPEECH_PROVIDER', 'disabled')
    api('/internal/speech/status', {'available': ready, 'provider': provider if ready else ''})
    if not ready:
        return False
    jobs = api('/internal/speech/claim', {}).get('jobs', [])
    if not jobs:
        return False
    job = jobs[0]
    identity = {'id': job['id'], 'lease': job['lease']}
    try:
        text = transcribe_audio(job['url'])
        api('/internal/speech/result', {**identity, 'text': text, 'provider': provider})
        print('{"speech_saved":true}', flush=True)
    except Exception:
        api('/internal/speech/result', {**identity, 'error': True})
        print('{"speech_failed":true}', flush=True)
    return True


if __name__ == '__main__':
    if len(TOKEN) < 32:
        raise SystemExit('Missing private speech worker credential.')
    while True:
        try:
            busy = cycle()
        except Exception:
            busy = False
            print('{"speech_worker_waiting":true}', flush=True)
        time.sleep(5 if busy else 60)
