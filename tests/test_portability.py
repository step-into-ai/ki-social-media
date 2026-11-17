import contextlib
import importlib.util
import io
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'collector'))
import provider
import transcriber
import translator


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class PortableTests(unittest.TestCase):
    def test_empty_install_has_no_personal_sources_and_ai_discovery_is_opt_in(self):
        service = load('portable_service', 'collector/service.py')
        with tempfile.TemporaryDirectory() as directory:
            service.DATA = pathlib.Path(directory);service.initialize()
            self.assertEqual(service.sources(), [])
            self.assertFalse(service.newsroom.settings()['enabled'])

    def test_without_ai_original_news_is_available(self):
        service = load('original_service', 'collector/service.py')
        with tempfile.TemporaryDirectory() as directory:
            service.DATA = pathlib.Path(directory);service.initialize()
            with service.db() as db:
                ident = db.execute("INSERT INTO sources(platform,handle,title,mode) VALUES('x','creator','Creator','posts')").lastrowid
            source = {**service.sources()[0], 'id': ident}
            service.save_success(source, [{'external_id': '1990000000000000000', 'author': 'creator', 'text': 'Original substantive news text.',
                'url': 'https://x.com/creator/status/1990000000000000000', 'published_at': '2026-11-17T12:00:00Z', 'media': []}], {}, [])
            with patch.object(service, 'AI_ENABLED', False):
                self.assertEqual(service.news()[0]['translation_status'], 'original')
                self.assertEqual(service.news()[0]['text'], 'Original substantive news text.')

    def test_configurable_chat_endpoint_and_model_with_no_key_for_local_provider(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def do_POST(self):
                requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length']))), self.headers.get('Authorization')))
                raw = json.dumps({'choices': [{'message': {'content': '{"ok":true}'}}]}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            with patch.dict(os.environ, {'AI_BASE_URL': 'http://127.0.0.1:' + str(server.server_port) + '/v1',
                'AI_MODEL': 'operator-selected-model', 'AI_API_KEY': '', 'AI_ALLOW_HTTP': 'true'}):
                self.assertEqual(provider.chat_json([{'role': 'user', 'content': 'Synthetic test'}]), {'ok': True})
            self.assertEqual(requests[0][0], '/v1/chat/completions')
            self.assertEqual(requests[0][1]['model'], 'operator-selected-model')
            self.assertIsNone(requests[0][2])
        finally:server.shutdown();server.server_close();thread.join()

    def test_provider_rejects_credential_urls_and_unapproved_cleartext(self):
        for url in ('http://remote.example/v1', 'https://user:password@example.com/v1', 'https://example.com/v1?token=secret'):
            with self.assertRaises(ValueError):provider.endpoint(url, 'chat/completions')

    def test_translation_validates_identity_and_preserves_urls(self):
        job = {'id': 'one', 'text_hash': 'digest', 'text': 'Read https://example.org/story'}
        for answer in ({'translations': [{'id': 'other', 'text_de': 'Text'}]}, {'translations': [{'id': 'one', 'text_de': 'Text without the original URL'}]}):
            with patch.object(translator, 'chat_json', return_value=answer):
                with self.assertRaises(ValueError):translator.translate([job])

    def test_unconfigured_speech_does_not_claim_or_download(self):
        with patch.dict(os.environ, {'SPEECH_PROVIDER': 'disabled'}), patch.object(transcriber, 'api', return_value={}) as api, patch.object(transcriber, 'transcribe_audio') as audio:
            self.assertFalse(transcriber.cycle());audio.assert_not_called()
            self.assertEqual(api.call_count, 1)

    def test_configurable_speech_upload_and_model(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def do_POST(self):
                received.append((self.path, self.rfile.read(int(self.headers['Content-Length'])), self.headers.get('Authorization')))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"text":"A complete synthetic audio transcript."}')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                audio = pathlib.Path(directory) / 'audio.m4a';audio.write_bytes(b'synthetic-audio')
                with patch.dict(os.environ, {'SPEECH_PROVIDER': 'compatible', 'SPEECH_BASE_URL': 'http://127.0.0.1:' + str(server.server_port) + '/custom',
                    'SPEECH_MODEL': 'operator-speech-model', 'SPEECH_API_KEY': '', 'SPEECH_ALLOW_HTTP': 'true'}):
                    self.assertEqual(transcriber.transcribe_file(audio), 'A complete synthetic audio transcript.')
            self.assertEqual(received[0][0], '/custom/audio/transcriptions')
            self.assertIn(b'operator-speech-model', received[0][1])
            self.assertIn(b'synthetic-audio', received[0][1])
            self.assertIsNone(received[0][2])
        finally:server.shutdown();server.server_close();thread.join()

    def test_failed_audio_download_removes_its_private_temporary_directory(self):
        folders = []
        def fail(args, **kwargs):
            folders.append(pathlib.Path(args[args.index('-o') + 1]).parent)
            return type('Result', (), {'returncode': 1})()
        with patch.object(transcriber, 'available', return_value=True), patch.object(transcriber.subprocess, 'run', side_effect=fail):
            with self.assertRaises(ValueError):transcriber.transcribe_audio('https://www.youtube.com/watch?v=abcdefghijk')
        self.assertTrue(folders)
        self.assertTrue(all(not folder.exists() for folder in folders))

    def test_init_preserves_credentials_and_backups_restore_whole_database(self):
        manager = load('instance_manager', 'tools/manage.py')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = pathlib.Path(directory)
            (root / '.env.example').write_text((ROOT / '.env.example').read_text())
            with patch.object(manager, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                manager.init('https://my-server.example')
                before = (root / '.env').read_bytes()
                with self.assertRaises(ValueError):manager.init('https://other.example')
                self.assertEqual(before, (root / '.env').read_bytes())
                manager.pair(False)
                pairing = json.loads((root / 'data/pairing.json').read_text())
                self.assertGreater(pairing['expires'], time.time())
                self.assertNotIn(pairing['code'], before.decode())
                with contextlib.closing(sqlite3.connect(root / 'data/cody-social.db')) as db:db.execute('CREATE TABLE example(value)');db.execute('INSERT INTO example VALUES(1)');db.commit()
                manager.backup();snapshot = next((root / 'data/backups').glob('*.db'))
                with contextlib.closing(sqlite3.connect(root / 'data/cody-social.db')) as db:db.execute('DELETE FROM example');db.commit()
                with self.assertRaises(ValueError):manager.restore(snapshot, False)
                manager.restore(snapshot, True)
                with contextlib.closing(sqlite3.connect(root / 'data/cody-social.db')) as db:self.assertEqual(db.execute('SELECT value FROM example').fetchone()[0], 1)

    def test_pairing_file_rotates_without_restarting_or_changing_instance_token(self):
        service = load('pairing_service', 'collector/service.py')
        with tempfile.TemporaryDirectory() as directory:
            service.DATA = pathlib.Path(directory)
            for code in ('first-random-code', 'second-random-code'):
                (service.DATA / 'pairing.json').write_text(json.dumps({'code': code, 'expires': time.time() + 600}))
                self.assertEqual(service.pairing()[0], code)


if __name__ == '__main__':unittest.main()
