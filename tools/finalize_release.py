"""Validate and package a local release candidate; public approval is separate."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
import yaml
import win32api
from source_manifest import application_source_files
from check_portable_release import verify as verify_portable
from download_dependency_sources import load_sources

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_QT = {'Core', 'Gui', 'Network', 'OpenGL', 'OpenGLWidgets', 'Positioning',
               'PrintSupport', 'Qml', 'QmlMeta', 'QmlModels', 'QmlWorkerScript',
               'Quick', 'QuickWidgets', 'Svg', 'WebChannel', 'WebEngineCore', 'WebEngineWidgets', 'Widgets'}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def archive(path, entries, compression):
    print(f'Creating and checking {path.name} ({len(entries)} files)', flush=True)
    pending = path.with_suffix('.partial.zip')
    with zipfile.ZipFile(pending, 'w', compression=compression, allowZip64=True) as z:
        for file, name in sorted(entries, key=lambda pair: pair[1]):
            z.write(file, name)
    with zipfile.ZipFile(pending) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f'ZIP CRC check failed: {bad}')
    pending.replace(path)
    print(f'ZIP CRC verification passed: {path.name}', flush=True)
    return {'filename': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path), 'crc_check': 'passed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-results', type=Path, required=True)
    parser.add_argument('--zip', action='store_true')
    parser.add_argument('--source-zips', action='store_true', help='Also create source archives (separate from the portable ZIP)')
    parser.add_argument('--for-publication', action='store_true')
    args = parser.parse_args()
    approvals = json.loads((ROOT / 'release-approvals.json').read_text(encoding='utf-8'))
    authorized = approvals.get('publication_authorization', {}).get('status') == 'confirmed'
    publication_notes = {k: v for k, v in approvals.items() if v['status'] != 'confirmed'}
    if args.for_publication and not authorized:
        raise SystemExit('Public release requires the project owner publication authorization')
    dist = ROOT / 'dist/HAMLET'
    companion = ROOT / 'dist/source-companion'
    tests = json.loads(args.test_results.read_text(encoding='utf-8'))
    execution = json.loads(args.test_results.with_name('execution.json').read_text(encoding='utf-8'))
    assert execution['exit_code'] == 0 and execution['executable_sha256'] == sha(dist / 'HAMLET.exe'), 'Tests belong to a different or failed EXE'
    assert len(tests) >= 11 and all(t['status'] == 'passed' for t in tests), 'Incomplete or failed executable tests'
    assert any(t['test'] == 'Release version, author credits and GPL notice' for t in tests)
    citation = yaml.safe_load((ROOT / 'CITATION.cff').read_text(encoding='utf-8'))
    assert citation['version'] == '1.0' and citation['license'] == 'GPL-3.0-only'
    assert len(citation['authors']) == 4
    version = win32api.GetFileVersionInfo(str(dist / 'HAMLET.exe'), r'\StringFileInfo\040904B0\FileVersion')
    assert version == '1.0.0.0', f'Unexpected executable version: {version}'
    assert sha(dist / 'LICENSE.txt') == sha(ROOT / 'third_party_licenses/common/GPL-3.0.txt'), 'Application GPL text changed'
    notice_text = (dist / 'NOTICE.txt').read_text(encoding='utf-8')
    assert 'GPL-3.0-only' in notice_text
    assert not any(key.lower() == 'doi' for key in citation), 'Publication identifier present in citation metadata'
    assert 'https://github.com/JonAndoniFdez/HAMLET' in (dist / 'README.txt').read_text(encoding='utf-8')
    for author in citation['authors']:
        assert author['given-names'] + ' ' + author['family-names'] in notice_text
    for name in ('LICENSE', 'Version.txt', 'models/hand/pose_deploy.prototxt', 'models/hand/pose_iter_102000.caffemodel'):
        assert sha(dist / 'openpose' / name) == sha(ROOT / 'openpose' / name), f'OpenPose file changed: {name}'
    model_notice = (dist / 'OPENPOSE_MODELS_NOTICE.txt').read_text(encoding='utf-8')
    for name in ('pose_deploy.prototxt', 'pose_iter_102000.caffemodel'):
        assert sha(dist / 'openpose/models/hand' / name) in model_notice, f'Model notice hash mismatch: {name}'
    qt = {p.stem[3:] for p in (dist / 'PySide6').glob('Qt6*.dll')}
    assert qt == EXPECTED_QT, f'Unexpected Qt set: extra={qt-EXPECTED_QT}, missing={EXPECTED_QT-qt}'
    assert not (dist / 'PySide6/qml').exists(), 'Unexpected QML tree'
    assert not list(dist.glob('api-ms-*.dll')), 'Unexpected copied Windows system files'
    for name in ('icuuc.dll', 'icudt78.dll', 'libssl-3-x64.dll', 'libcrypto-3-x64.dll', 'avcodec-60.dll'):
        assert not (dist / name).exists(), f'Unexpected root runtime: {name}'
    assert not list(dist.rglob('opencv_videoio_ffmpeg*.dll'))
    assert not list(dist.rglob('pi_win_proxy_loaderd.dll'))
    for name, digest in json.loads((dist / 'build-inputs.json').read_text()).items():
        assert sha(ROOT / name) == digest, f'Application changed since build: {name}'
    subprocess.run([sys.executable, str(ROOT / 'tools/verify_release_preview.py'), str(dist / 'HAMLET.exe')], check=True)
    notices = json.loads((dist / 'third_party_licenses/dependency-licenses.json').read_text(encoding='utf-8'))
    for package in notices['packages']:
        for notice in package['notices']:
            assert sha(dist / notice['file']) == notice['sha256'], notice['file']
    for name in ('LICENSE.txt', 'THIRD_PARTY_LICENSES.txt', 'NOTICE.txt', 'THIRD_PARTY_NOTICES.md', 'SOURCE_CODE.md', 'docs/README.pdf', 'CITATION.cff', 'OPENPOSE_MODELS_NOTICE.txt'):
        assert sha(dist / name) == sha(ROOT / name), f'Outdated release document: {name}'
    assert sha(dist / 'README.txt') == sha(ROOT / 'README_RELEASE.txt'), 'Outdated README'
    credits = dist / 'third_party_licenses/QtWebEngine-credits.html'
    assert credits.stat().st_size > 100000 and 'Redistribution' in credits.read_text(encoding='utf-8')
    assert sha(credits) == sha(ROOT / 'third_party_licenses/QtWebEngine-credits.html')
    source_entries = []
    source_versions = {}
    pinned_sources = {item['path']: item for item in load_sources(ROOT / 'third_party_licenses/SOURCE_DOWNLOADS.json')}
    verified_paths = set()
    for relative in ('SOURCES.json', 'native/SOURCES.json'):
        manifest = companion / relative
        sources = json.loads(manifest.read_text(encoding='utf-8'))['sources']
        source_entries.append((manifest, relative))
        for item in sources:
            assert item['status'] == 'downloaded', item
            path = manifest.parent / item['filename']
            assert sha(path) == item['sha256'], path
            source_path = path.relative_to(companion).as_posix()
            assert source_path in pinned_sources, f'Source archive missing from public catalog: {source_path}'
            pinned = pinned_sources[source_path]
            assert all(pinned[key] == item[key] for key in ('name', 'version', 'sha256', 'bytes', 'url')), f'Outdated public source catalog: {source_path}'
            verified_paths.add(source_path)
            source_entries.append((path, path.relative_to(companion).as_posix()))
            if relative == 'SOURCES.json':
                source_versions[re.sub(r'[-_.]+', '-', item['name'].lower())] = item['version']
    assert verified_paths == set(pinned_sources), 'Public source catalog and retained archives differ'
    source_aliases = {'pyside6': 'qtforpython', 'pyside6-addons': 'qtforpython',
                      'pyside6-essentials': 'qtforpython', 'shiboken6': 'qtforpython'}
    for package in notices['packages']:
        name = re.sub(r'[-_.]+', '-', package['name'].lower())
        assert source_versions.get(source_aliases.get(name, name)) == package['version'], f'Missing exact source version: {name}=={package["version"]}'
    assert source_versions['python'] == notices['python_version']
    blender_version = subprocess.check_output([str(dist / 'blender/blender.exe'), '--version'], text=True, timeout=30).splitlines()[0].strip()
    assert blender_version == 'Blender ' + source_versions['blender'], f'Blender sources do not match: {blender_version}'
    copied_notices = json.loads((ROOT / 'third_party_licenses/upstream-sources/MANIFEST.json').read_text())['files']
    for item in copied_notices:
        assert sha(dist / 'third_party_licenses' / item['notice']) == item['sha256'], item['notice']
    print('Executable, Qt selection, original notices and source archive hashes verified', flush=True)
    provenance = {'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'version': citation['version'], 'windows_version': version,
                  'own_code_license': citation['license'],
                  'working_tree_snapshot': True, 'python_version': sys.version.split()[0],
                  'requirements_lock_sha256': sha(ROOT / 'requirements-release.lock.txt'),
                  'executable_sha256': sha(dist / 'HAMLET.exe'),
                  'qt_modules': sorted(qt), 'tests': tests,
                  'test_execution': execution,
                  'dependency_archives': len(source_entries)-2,
                  'publication_status': 'owner_authorized' if authorized else 'local_candidate',
                  'publication_notes': publication_notes}
    files = [{'path': p.relative_to(dist).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(dist.rglob('*')) if p.is_file() and p.name != 'release-manifest.json']
    write_json(dist / 'release-manifest.json', {'provenance': provenance, 'files': files})
    report = {'technical_validation': 'passed', **provenance, 'file_count': len(files), 'uncompressed_bytes': sum(f['bytes'] for f in files)}
    report['portable_content_checks'] = verify_portable(dist)
    if args.zip:
        artifacts = []
        artifacts.append(archive(ROOT / 'dist/HAMLET.zip', [(p, p.relative_to(dist).as_posix()) for p in dist.rglob('*') if p.is_file()], zipfile.ZIP_DEFLATED))
        if args.source_zips:
            source_entries.append((ROOT / 'SOURCE_CODE.md', 'SOURCE_CODE.md'))
            artifacts.append(archive(ROOT / 'dist/HAMLET-dependency-sources.zip', source_entries, zipfile.ZIP_STORED))
            application = [(p, p.relative_to(ROOT).as_posix()) for p in application_source_files(ROOT)]
            artifacts.append(archive(ROOT / 'dist/HAMLET-application-source.zip', application, zipfile.ZIP_DEFLATED))
        report['artifacts'] = artifacts
        (ROOT / 'dist/SHA256SUMS.txt').write_text(''.join(f"{a['sha256']}  {a['filename']}\n" for a in artifacts), encoding='ascii')
    write_json(ROOT / 'dist/RELEASE_VALIDATION.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in {'tests', 'publication_notes'}}, indent=2))


if __name__ == '__main__':
    main()
