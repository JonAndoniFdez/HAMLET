"""WebEngine needs positioning symbols, but HAMLET does not access GPS devices."""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, dest) for source, dest in binaries if '/plugins/position' not in dest.replace('\\', '/')]
