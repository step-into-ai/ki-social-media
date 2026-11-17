"""Create this application's update identity once. Back up .signing privately."""
import os
import pathlib
import secrets
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[1] / 'android/.signing'
root.mkdir(mode=0o700, exist_ok=True)
key = root / 'ki-social-media.p12'
props = root / 'signing.properties'
if key.exists() or props.exists():
    if not (key.exists() and props.exists()):
        raise SystemExit('Incomplete signing identity. Do not overwrite it.')
    print('Existing KI Social Media signing identity preserved.')
else:
    suffix = '.exe' if os.name == 'nt' else ''
    java = pathlib.Path(os.environ.get('JAVA_HOME', '')) / 'bin' / ('keytool' + suffix)
    tool = str(java) if java.is_file() else shutil.which('keytool')
    if not tool:raise SystemExit('Set JAVA_HOME to JDK 17 or later.')
    password = secrets.token_urlsafe(40)
    result = subprocess.run([tool, '-genkeypair', '-keystore', str(key), '-storetype', 'PKCS12',
        '-alias', 'ki-social-media', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000',
        '-dname', 'CN=KI Social Media, O=StepIntoAI, C=DE', '-storepass:env', 'KI_SIGNING_PASSWORD',
        '-keypass:env', 'KI_SIGNING_PASSWORD'], env={**os.environ, 'KI_SIGNING_PASSWORD': password}, capture_output=True)
    if result.returncode:raise SystemExit('Could not create signing identity.')
    props.write_text('storePassword=' + password + '\nkeyPassword=' + password + '\n', encoding='utf-8')
    key.chmod(0o600);props.chmod(0o600)
    print('Created a separate private update identity for de.stepintoai.kisocial.')
