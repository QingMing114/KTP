"""Install verified source and dist overlays while retaining old hashed assets."""
import hashlib, json, shutil, sqlite3, tarfile
from pathlib import Path
release=Path('/data/yuehao/apps/ktp/releases/workspace-flow-20261012')
app=Path('/data/yuehao/apps/ktp/app').resolve()
checks=json.loads((release/'checksums.json').read_text())
files=json.loads((release/'files.json').read_text())
c=sqlite3.connect('/data/yuehao/apps/ktp/data/ktp_v2_runtime.sqlite3')
running=[w['workflow_id'] for (s,) in c.execute('SELECT payload_json FROM product_analysis_workflows') if (w:=json.loads(s))['status']=='running']
assert not running, 'Active workflows must finish before backend restart'
backup=release/'backup'
assert not backup.exists(), 'Release backup already exists; do not overwrite'
backup.mkdir()
for name in files+['frontend/dist/index.html']:
    target=(app/name).resolve()
    assert target.is_relative_to(app)
    if target.is_file():
        saved=backup/name
        saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(target,saved)
with tarfile.open(release/'package.tar.gz') as tar:
    names={member.name for member in tar.getmembers()}
    assert names==set(checks)
    # Publish the HTML entry only after every new module is in place.
    ordered=sorted(checks,key=lambda name:name=='frontend/dist/index.html')
    for name in ordered:
        target=(app/name).resolve()
        assert target.is_relative_to(app)
        data=tar.extractfile(name).read()
        assert hashlib.sha256(data).hexdigest()==checks[name],name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
assert all(hashlib.sha256((app/name).read_bytes()).hexdigest()==expected for name,expected in checks.items())
print(json.dumps({'installed_files':len(checks),'source_and_dist_match':True,'old_assets_retained':True,'running_workflows':len(running),'backup':str(backup)}))
