"""Generate an offline index from the exact Qt source notices, not a live website."""
import hashlib
import html
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
NOTICES = ROOT / 'third_party_licenses'
QT = NOTICES / 'upstream-sources/Qt-6.10.2'
manifest_path = NOTICES / 'upstream-sources/MANIFEST.json'
manifest = json.loads(manifest_path.read_text())
missing = set()
for path in QT.rglob('qt_attribution.json'):
    try:
        items = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        continue
    for item in items if isinstance(items, list) else [items]:
        value = item.get('LicenseFile', [])
        for name in value if isinstance(value, list) else [value]:
            target = (path.parent / name).resolve()
            if target.is_relative_to(QT) and not target.is_file():
                missing.add(target.relative_to(QT).as_posix())
if missing:
    with tarfile.open(ROOT / 'dist/source-companion/qt-everywhere-src-6.10.2.tar.xz', 'r|xz') as archive:
        for member in archive:
            relative = '/'.join(member.name.split('/')[1:])
            if member.isfile() and relative in missing:
                data = archive.extractfile(member).read()
                target = QT / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                manifest['files'].append({'source': 'qt-everywhere-src-6.10.2.tar.xz',
                                          'original_path': member.name,
                                          'notice': target.relative_to(NOTICES).as_posix(),
                                          'sha256': hashlib.sha256(data).hexdigest()})
                missing.remove(relative)
    if missing:
        raise RuntimeError(f'Unresolved Qt attribution license files: {sorted(missing)}')
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
files = sorted(p for p in (QT / 'qtwebengine').rglob('*') if p.is_file() and p.name != 'qt_attribution.json')
parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Qt WebEngine and Chromium source notices</title>',
         '<style>body{font:16px/1.5 system-ui;max-width:1000px;margin:40px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{overflow-wrap:anywhere;font-size:18px}</style>',
         '<h1>Qt WebEngine 6.10.2 and Chromium source notices</h1>',
         '<p>Original license and copyright notices from qt-everywhere-src-6.10.2.tar.xz. Includes source/build components and other platforms that may not be present in the binary. This is a source-notice superset, not a claim that every component is shipped.</p>',
         '<p>Original byte-for-byte files are linked below. The complete source archive and build files accompany this release. Additional Qt module notices are in the <a href="index.html">main license index</a>.</p>']
for path in files:
    data = path.read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        text = data.decode('latin1')
    rel = path.relative_to(NOTICES).as_posix()
    parts.append('<details><summary>' + html.escape(rel) + '</summary><p><a href="' + html.escape(rel, quote=True) + '">Original notice file</a></p><pre>' + html.escape(text) + '</pre></details>')
parts.append('</html>')
(NOTICES / 'QtWebEngine-credits.html').write_text('\n'.join(parts), encoding='utf-8')
print(f'Offline WebEngine credits contain {len(files)} original source notices')
