"""Resolve Blender dependency source URLs from its exact upstream build recipes."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
from fetch_release_sources import fetch

ROOT = Path(__file__).resolve().parents[1]


def main():
    cmake = ROOT / 'third_party_licenses/upstream-sources/Blender-4.3.2/build_files/build_environment/cmake/versions.cmake'
    values = {}
    for key, raw in re.findall(r'^set\((\w+)\s+([^\n]*?)\)[ \t]*(?:#[^\n]*)?$', cmake.read_text(), re.M):
        value = raw.strip().strip('"')
        for _ in range(5):
            value = re.sub(r'\$\{(\w+)\}', lambda m: values.get(m[1], m[0]), value)
        values[key] = value
    items = []
    for key, filename in values.items():
        if not key.endswith('_FILE'):
            continue
        prefix = key[:-5]
        license_name = values.get(prefix + '_LICENSE', '')
        if not license_name or prefix + '_DEPSBUILDTIMEONLY' in values:
            continue
        item = {'name': 'Blender-' + prefix, 'version': values.get(prefix + '_VERSION', ''),
                'filename': filename, 'license': license_name,
                'url': 'https://projects.blender.org/blender/lib-source/media/branch/blender-v4.3-release/' + filename,
                'upstream_url': values.get(prefix + '_URI', ''),
                'recipe_hash': values.get(prefix + '_HASH'),
                'recipe_hash_type': values.get(prefix + '_HASH_TYPE', '').lower()}
        items.append(item)
    folder = ROOT / 'dist/source-companion/native'
    folder.mkdir(exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lambda item: fetch(item, folder), items):
            if result['status'] == 'downloaded' and result['recipe_hash']:
                with (folder / result['filename']).open('rb') as stream:
                    actual = hashlib.file_digest(stream, result['recipe_hash_type']).hexdigest()
                if actual != result['recipe_hash']:
                    result.update(status='failed', error='Hash differs from Blender build recipe')
            results.append(result)
            (folder / 'SOURCES.json').write_text(json.dumps({'scope': 'Blender dependency sources with declared licenses from its 4.3.2 build recipes, excluding explicit build-time-only dependencies; patches and build scripts are in blender-4.3.2.tar.xz. Includes components for other platforms.', 'sources': results}, indent=2), encoding='utf-8')
    if any(r['status'] != 'downloaded' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
