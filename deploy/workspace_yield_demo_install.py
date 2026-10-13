"""Stage the verified overlay; publish index only after backend health checks."""
import hashlib
import json
import shutil
import sqlite3
import tarfile
from pathlib import Path

release = Path('/data/yuehao/apps/ktp/releases/workspace-yield-demo-20261013')
app = Path('/data/yuehao/apps/ktp/app').resolve()
checks = json.loads((release/'checksums.json').read_text())
files = json.loads((release/'files.json').read_text())
with sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3') as connection:
    running = [item['workflow_id'] for (raw,) in connection.execute('SELECT payload_json FROM product_analysis_workflows') if (item:=json.loads(raw))['status']=='running']
    submissions = connection.execute("SELECT COUNT(*) FROM product_submissions WHERE status IN ('queued','running')").fetchone()[0]
assert not running and not submissions, 'Active work must finish before backend restart'
backup = release/'backup'
assert not backup.exists(), 'Do not overwrite an existing release backup'
with tarfile.open(release/'package.tar.gz') as archive:
    assert {member.name for member in archive.getmembers()} == set(checks)
    contents = {name: archive.extractfile(name).read() for name in checks}
assert all(hashlib.sha256(data).hexdigest()==checks[name] for name,data in contents.items())
assert all((app/name).resolve().is_relative_to(app) for name in contents)
backup.mkdir()
for name in files+['frontend/dist/index.html']:
    path = (app/name).resolve()
    if path.is_file():
        saved = backup/name
        saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,saved)
for name,data in contents.items():
    target = release/'pending-index.html' if name=='frontend/dist/index.html' else (app/name).resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(data)
assert all(hashlib.sha256((app/name).read_bytes()).hexdigest()==expected for name,expected in checks.items() if name!='frontend/dist/index.html')
print(json.dumps({'staged_files':len(checks),'backup':str(backup),'index_pending':True,'old_assets_retained':True}))
