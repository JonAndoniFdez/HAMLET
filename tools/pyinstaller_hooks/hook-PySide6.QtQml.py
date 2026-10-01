"""Keep QtQml's native dependencies without collecting every installed QML plugin.

HAMLET embeds QWebEngineView in Widgets; it never loads an application QML file.
If a future feature does, add its specific QML imports and test the frozen app.
"""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, dest) for source, dest in binaries if '/plugins/qmltooling' not in dest.replace('\\', '/')]
