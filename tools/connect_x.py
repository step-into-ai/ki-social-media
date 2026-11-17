"""Import exactly two user-provided X cookies into this instance's dedicated browser."""
import getpass
import os
import pathlib
import re
import time


def main():
    if not os.isatty(0):
        raise SystemExit('Use an interactive terminal; do not pass session values as command arguments.')
    data = pathlib.Path(os.environ.get('CODY_DATA', pathlib.Path(__file__).resolve().parents[1] / 'data'))
    home = data / 'reach'
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ['HOME'] = str(home)
    os.environ['USERPROFILE'] = str(home)
    print('Only use your own X session. These values grant account access and stay in this instance.')
    print('Copy auth_token and ct0 from x.com in your own browser\'s developer storage view.')
    values = {name: getpass.getpass(name + ': ').strip() for name in ('auth_token', 'ct0')}
    if any(not re.fullmatch(r'[a-fA-F0-9]{20,512}', value) for value in values.values()):
        values.clear()
        raise SystemExit('Invalid session values. Nothing imported.')
    from agent_reach.runtime import browser, cdp
    try:
        browser.ensure_running()
        cookies = [{'name': name, 'value': value, 'domain': '.x.com', 'path': '/', 'secure': True,
            'httpOnly': name == 'auth_token', 'sameSite': 'None', 'expires': time.time() + 30 * 86400}
            for name, value in values.items()]
        if cdp.call('Storage.setCookies', {'cookies': cookies}) is None:
            raise ValueError('Session import was not confirmed.')
        browser.save_session()
    except Exception:
        raise SystemExit('Session import was not confirmed. Review the dedicated browser setup; no raw response was logged.') from None
    finally:
        values.clear()
        browser.stop()
    for path in home.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.sqlite', '.db'):
            path.chmod(0o600)
    print('Session saved. Validate a real X fetch before calling the source connected.')


if __name__ == '__main__':main()
