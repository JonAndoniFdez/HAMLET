"""Preserve source notices without extracting executable code or unsafe paths."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'dist/source-companion'
OUT = ROOT / 'third_party_licenses/upstream-sources'
PATTERN = re.compile(r'^(license(?:s|ref)?|licence|copying|copyright|notice|authors)(?:[._-]|$)', re.I)


def main():
    records = []
    sources = json.loads((SOURCE / 'SOURCES.json').read_text())['sources']
    for item in sources:
        if item['status'] != 'downloaded':
            raise RuntimeError(item)
        archive = SOURCE / item['filename']
        if not tarfile.is_tarfile(archive):
            continue
        component = re.sub(r'[^A-Za-z0-9_.-]', '_', item['name'] + '-' + item['version'])
        count = 0
        with tarfile.open(archive, 'r|*') as tar:
            for member in tar:
                relative = PurePosixPath(member.name)
                if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
                    continue
                selected = (PATTERN.search(relative.name) or any(p.lower() == 'licenses' for p in relative.parts)
                            or relative.name == 'qt_attribution.json'
                            or (item['name'] == 'Blender' and '/build_environment/' in member.name)
                            or (item['name'] == 'Python' and '/PCbuild/' in member.name and relative.suffix in {'.bat', '.props'}))
                if not selected or member.size > 10 * 1024 * 1024:
                    continue
                data = tar.extractfile(member).read()
                target = OUT / component / Path(*relative.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                records.append({'source': item['filename'], 'original_path': member.name,
                                'notice': target.relative_to(ROOT / 'third_party_licenses').as_posix(),
                                'sha256': hashlib.sha256(data).hexdigest()})
                count += 1
        print(component, count, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'MANIFEST.json').write_text(json.dumps({'scope': 'Unmodified upstream notices; includes build-only and unused source components, not an assertion that all are shipped.', 'files': records}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
