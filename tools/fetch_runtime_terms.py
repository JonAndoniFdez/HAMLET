"""Save Microsoft runtime terms from their official published document."""
from io import BytesIO
from pathlib import Path
import urllib.request
from xml.etree import ElementTree
import zipfile

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'third_party_licenses/Microsoft'
folder.mkdir(parents=True, exist_ok=True)
for name, url in {
    'Visual-C-Runtime-2015-2022': 'https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx',
    'Visual-Studio-2022-Community': 'https://visualstudio.microsoft.com/wp-content/uploads/2021/11/Visual-Studio-2022-Community-License-EN.docx',
}.items():
    data = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read()
    with zipfile.ZipFile(BytesIO(data)) as archive:
        tree = ElementTree.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = [''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in tree.findall('.//w:p', ns)]
    (folder / (name + '.txt')).write_text('Text extracted without substantive edits from:\n' + url + '\n\n' + '\n'.join(paragraphs), encoding='utf-8')
url = 'https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution'
(folder / 'Visual-Studio-2022-REDIST.html').write_bytes(urllib.request.urlopen(url, timeout=60).read())
print('Saved original runtime terms, development license and redistribution list')
