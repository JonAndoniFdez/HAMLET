"""Keep image/UI plugins, without the unused virtual keyboard and PDF decoder."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, dest) for source, dest in binaries
            if Path(source).name.lower() not in {'qtvirtualkeyboardplugin.dll', 'qpdf.dll'}]
