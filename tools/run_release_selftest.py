"""Run the frozen program without development PATH/PYTHONPATH and attest the result."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    exe, out = args.executable.resolve(), args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Use an empty output directory; never overwrite existing project data or test results')
    out.mkdir(parents=True, exist_ok=True)
    with exe.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                'QT_QPA_PLATFORM_PLUGIN_PATH', 'QTWEBENGINEPROCESS_PATH',
                'QTWEBENGINE_RESOURCES_PATH', 'QTWEBENGINE_CHROMIUM_FLAGS'):
        env.pop(key, None)
    env['PATH'] = os.pathsep.join([str(Path(env['WINDIR']) / 'System32'), env['WINDIR']])
    env['PYTHONNOUSERSITE'] = '1'
    env['QT_QPA_PLATFORM'] = 'windows'
    with tempfile.TemporaryDirectory(prefix='hamlet-release-check-') as work:
        result = subprocess.run([str(exe), '--self-test-release', str(out)], cwd=work, env=env,
                                timeout=240, creationflags=subprocess.CREATE_NO_WINDOW)
    execution = {'executable_sha256': digest, 'exit_code': result.returncode,
                 'isolated_working_directory': True, 'development_path_removed': True,
                 'scope': 'Frozen executable on this Windows host, not an independent clean Windows installation'}
    (out / 'execution.json').write_text(json.dumps(execution, indent=2), encoding='utf-8')
    if result.returncode:
        raise SystemExit(result.returncode)
    tests = json.loads((out / 'results.json').read_text(encoding='utf-8'))
    if len(tests) < 11 or any(item['status'] != 'passed' for item in tests):
        raise SystemExit('Incomplete self-test results')
    source = exe.parent / 'third_party_licenses/QtWebEngine-credits.html'
    assert source.stat().st_size > 100000
    print(f'{len(tests)} executable integration checks passed; offline Chromium credits accessible')


if __name__ == '__main__':
    main()
