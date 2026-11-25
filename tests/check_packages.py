"""Fail publication if source, licenses or entry points are missing, or external media leaked in."""
from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
wheel, = (root / 'dist').glob('*.whl')
source, = (root / 'dist').glob('*.tar.gz')
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    for item in ('aurora_boot/app.py', 'aurora_boot/animation.py', 'aurora_boot/windows.py', 'aurora_boot/config.py'):
        assert item in names, item
    assert any(name.endswith('/licenses/LICENSE') for name in names)
    assert any(name.endswith('/licenses/DEPENDENCIES.md') for name in names)
    assert any(name.endswith('/entry_points.txt') for name in names)
    assert not any(name.endswith(('.mp4', '.ttf', '.swift', '.cs')) for name in names)
with tarfile.open(source) as archive:
    names = archive.getnames()
    for suffix in ('/pyproject.toml', '/README.md', '/LICENSE', '/DEPENDENCIES.md', '/src/aurora_boot/app.py'):
        assert any(name.endswith(suffix) for name in names), suffix
print('PASS: wheel and source contain the independent application, licenses and entry points; no inherited media or native source.')
