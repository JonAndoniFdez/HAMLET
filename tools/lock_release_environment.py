"""Pin the installed dependency closure used to create this release."""
import importlib.metadata as metadata
import json
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
pending = ['PyInstaller', 'pyinstaller-hooks-contrib', 'PySide6', 'numpy', 'pandas',
           'scipy', 'opencv-python', 'Pillow', 'openpyxl', 'xlrd', 'vedo', 'vtk',
           'trimesh', 'pyvista', 'pyvistaqt', 'PyYAML', 'psutil', 'pywin32']
packages = {}
inventory = ROOT / 'output/dependency_audit/inventory.json'
if inventory.is_file():
    pending += [item['name'] for item in json.loads(inventory.read_text(encoding='utf-8'))['packages']]
while pending:
    name = canonicalize_name(pending.pop())
    if name in packages:
        continue
    dist = metadata.distribution(name)
    packages[name] = dist.version
    for raw in dist.requires or []:
        req = Requirement(raw)
        if req.marker is None or req.marker.evaluate({'extra': ''}):
            installed = metadata.version(req.name)
            if req.specifier and installed not in req.specifier:
                raise RuntimeError(f'Installed {req.name}=={installed} does not satisfy {req}')
            pending.append(req.name)
text = '# Windows x64 / CPython 3.11.9; captured from the validated release environment.\n'
text += '# Includes build tools and dependency closure; not every package is shipped.\n'
text += '\n'.join(f'{name}=={version}' for name, version in sorted(packages.items())) + '\n'
(ROOT / 'requirements-release.lock.txt').write_text(text, encoding='utf-8')
print(f'Pinned {len(packages)} installed packages')
