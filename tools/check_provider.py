"""Optional operator-run check. Sends only a synthetic phrase to the configured provider."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'collector'))
from provider import chat_json

if __name__ == '__main__':
    result = chat_json([{'role': 'system', 'content': 'Return only JSON: {"ok":true}.'},
                        {'role': 'user', 'content': 'This is a synthetic connectivity check.'}], 128)
    if result.get('ok') is not True:raise SystemExit('Provider returned unexpected JSON.')
    print('Configured chat endpoint returned valid JSON.')
