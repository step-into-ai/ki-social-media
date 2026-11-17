"""Check versioned files for private runtime material before a push or release."""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    output = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    paths = [pathlib.Path(item.decode()) for item in output.split(b'\0') if item]
    if not paths:raise SystemExit('No versioned files to inspect. Stage the intended public files first.')
    issues = []
    for relative in paths:
        name = relative.as_posix()
        if (any(part in ('.signing', 'data', 'backups', '.venv', '.gradle', '.kotlin', 'dist', 'build') for part in relative.parts)
                or '.local.' in name or relative.suffix in ('.db', '.p12', '.jks', '.keystore', '.apk')
                or relative.name.startswith('.env') and relative.name != '.env.example'):
            issues.append(name + ': private/generated file')
        raw = (ROOT / relative).read_bytes()
        if b'\0' in raw:continue
        text = raw.decode('utf-8', errors='replace')
        if relative.name == 'release_check.py':continue
        for pattern in (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'gh[pousr]_[A-Za-z0-9]{30,}',
                        r'sk-(?:or-v1-)?[A-Za-z0-9_-]{30,}', r'C:[/\\]Users[/\\]',
                        r'spiesse-pi\.taile', r'/home/benny', r'/mnt/benny-data'):
            if re.search(pattern, text):issues.append(name + ': personal endpoint/path or credential pattern')
        if '\ufffd' in text:issues.append(name + ': invalid UTF-8 replacement character')
    if issues:
        print('\n'.join(issues), file=sys.stderr);raise SystemExit(1)
    print('Checked ' + str(len(paths)) + ' versioned public files: no private runtime material found.')


if __name__ == '__main__':main()
