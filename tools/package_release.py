"""Package only versioned backend sources, alongside a separately built signed APK."""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = '0.1.0-beta.1'


def main():
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit the reviewed source first; release archives must match a clean revision.')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    dist = ROOT / 'dist';dist.mkdir(exist_ok=True)
    apk = dist / ('KI-Social-Media-' + VERSION + '.apk')
    if not apk.is_file():raise SystemExit('Build and verify the signed APK first.')
    signer = shutil.which('apksigner')
    if not signer:
        signer = str(pathlib.Path(os.environ.get('ANDROID_HOME', '')) / 'build-tools/36.0.0' / ('apksigner.bat' if os.name == 'nt' else 'apksigner'))
    verified = subprocess.check_output([signer, 'verify', '--print-certs', str(apk)], cwd=ROOT, text=True)
    certificate = re.search(r'certificate SHA-256 digest: ([0-9a-fA-F]{64})', verified)
    if not certificate:raise SystemExit('Could not verify the APK signing certificate.')
    bundle = dist / ('KI-Social-Media-Backend-' + VERSION + '.zip')
    allowed = {'collector', 'tools', 'tests', 'deploy', 'docs', 'licenses'}
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in filter(None, names):
            path = pathlib.PurePosixPath(name)
            if len(path.parts) == 1 or path.parts[0] in allowed:
                content = subprocess.check_output(['git', 'show', revision + ':' + name], cwd=ROOT)
                archive.writestr('ki-social-media/' + name, content)
    info = {'version': VERSION, 'source_commit': revision, 'android_package': 'de.stepintoai.kisocial',
            'minimum_android_api': 29, 'server_architectures': ['linux/amd64', 'linux/arm64'],
            'apk_signing_certificate_sha256': certificate[1].lower(),
            'artifacts': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                          for p in (apk, bundle)}}
    manifest = dist / 'RELEASE-INFO.json';manifest.write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    (dist / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                                          for p in (apk, bundle, manifest)), encoding='utf-8')
    print('Packaged signed APK, backend sources, release manifest and SHA256SUMS for ' + revision)


if __name__ == '__main__':main()
