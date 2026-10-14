"""Install only the reviewed overlay, with source conflict checks and backups."""
import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--release', type=Path, required=True)
args = parser.parse_args()
release = args.release.resolve()
app = Path('/home/D/zhanghuaxiang_D/Code/KTP').resolve()
checks = json.loads((release / 'checksums.json').read_text())
before = json.loads((release / 'before.json').read_text())
for name, expected in before.items():
    target = (app / name).resolve()
    assert target.is_relative_to(app), name
    actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
    assert actual == expected, f'Server source changed since inspection: {name}'
backup = release / 'backup'
assert not backup.exists(), 'Do not overwrite a previous backup'
backup.mkdir()
new_files = []
for name in checks:
    target = (app / name).resolve()
    assert target.is_relative_to(app) and name != 'backend/.env', name
    if target.is_file():
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    else:
        new_files.append(name)
(release / 'new-files.json').write_text(json.dumps(new_files))
with tarfile.open(release / 'package.tar.gz') as tar:
    assert set(tar.getnames()) == set(checks)
    for name in sorted(checks, key=lambda name: name == 'frontend/dist/index.html'):
        data = tar.extractfile(name).read()
        assert hashlib.sha256(data).hexdigest() == checks[name], name
        target = (app / name).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.professional-mode-new')
        temporary.write_bytes(data)
        temporary.replace(target)
assert all(hashlib.sha256((app / name).read_bytes()).hexdigest() == value for name, value in checks.items())
result = {'installed_files': len(checks), 'backup': str(backup), 'source_conflicts': False, 'old_frontend_assets_retained': True}
(release / 'installation.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
