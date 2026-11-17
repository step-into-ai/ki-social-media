"""Optional, pinned local TikTok audio-language check; builds only in this instance's data."""
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = pathlib.Path(os.environ.get('CODY_DATA', pathlib.Path(__file__).resolve().parents[1] / 'data')) / 'tiktok-language'
COMMIT = 'd1be6fde11ac6e0407606b4e42fe72d34add8037'
SOURCE_SHA = '645445da884df6dbd52b30f82d7be7c01d1767c938714e477e786b88d529e9f4'
MODEL_SHA = '818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7'


def fetch(url, limit, digest):
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read(limit + 1)
    if len(data) > limit or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Download checksum or size does not match the pinned release.')
    return data


def main():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = ROOT / ('source-' + COMMIT)
    if not source.exists():
        archive = fetch('https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/' + COMMIT, 20_000_000, SOURCE_SHA)
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            total = 0
            for member in tar.getmembers():
                parts = pathlib.PurePosixPath(member.name).parts[1:]
                target = source.joinpath(*parts).resolve()
                if not target.is_relative_to(source.resolve()):raise ValueError('Invalid archive path.')
                if member.isdir():target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    total += member.size
                    if total > 200_000_000:raise ValueError('Source archive too large.')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
    build = ROOT / 'build'
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
        '-DBUILD_SHARED_LIBS=OFF', '-DWHISPER_BUILD_TESTS=OFF', '-DGGML_OPENMP=OFF', '-DGGML_NATIVE=OFF'], check=True)
    subprocess.run(['cmake', '--build', str(build), '--target', 'whisper-cli', '-j2'], check=True)
    shutil.copyfile(build / 'bin/whisper-cli', ROOT / 'whisper-cli')
    (ROOT / 'whisper-cli').chmod(0o700)
    model = ROOT / 'ggml-tiny-q5_1.bin'
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA:
        model.write_bytes(fetch('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny-q5_1.bin', 64_000_000, MODEL_SHA))
    model.chmod(0o600)
    (ROOT / 'provenance.json').write_text(json.dumps({'whisper_cpp_commit': COMMIT, 'source_sha256': SOURCE_SHA, 'model_sha256': MODEL_SHA}) + '\n')
    print('Pinned local speech-language check is ready.')


if __name__ == '__main__':main()
