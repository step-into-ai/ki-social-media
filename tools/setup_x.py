"""Prepare this instance's optional X channel with the regular packaged Chromium."""
import os
import shutil
import subprocess
import sys


def main():
    chromium = shutil.which('chromium')
    if not chromium:
        raise SystemExit('Install regular Chromium in this environment before preparing X.')
    from agent_reach.runtime import browser
    browser.update_state(backend='chrome', executable=chromium, launcher_python=None,
                         fallback_reason='Operator-selected regular packaged Chromium')
    result = subprocess.run(['agent-reach', 'add', 'twitter'], capture_output=True, text=True, timeout=480)
    if result.returncode:
        # Only intended for diagnosing a fresh, session-free setup. Do not print browser profiles.
        probe = subprocess.run([chromium, '--headless=new', '--disable-gpu', '--dump-dom', 'about:blank'],
                               capture_output=True, text=True, timeout=30)
        print('Regular Chromium launch exit code: ' + str(probe.returncode), file=sys.stderr)
        # Sandboxing diagnostics contain no cookies, URLs, profile state or account contents.
        for line in probe.stderr.splitlines():
            if any(word in line.lower() for word in ('sandbox', 'namespace', 'operation not permitted')):
                print(line[:500], file=sys.stderr)
        raise SystemExit('X browser setup did not succeed. Check container browser-sandbox support.')
    print('Regular Chromium and X toolkit are ready; no user session was imported.')


if __name__ == '__main__':main()
