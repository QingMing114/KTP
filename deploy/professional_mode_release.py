"""Inspect, package and synchronize the professional-mode overlay to gpu208."""
import difflib
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

APP = "/home/D/zhanghuaxiang_D/Code/KTP"
DATA = "/home/D/zhanghuaxiang_D/apps/ktp"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "_render_feedback" / "professional-mode-release"
OUT.mkdir(exist_ok=True)
FILES = json.loads((ROOT / "deploy/professional_mode_files.json").read_text())
PYTHON = "/home/D/zhanghuaxiang_D/.conda/envs/ktp/bin/python"


def remote(code):
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "kt-server-208", f"{PYTHON} -"],
                            input=code, text=True, encoding="utf-8", capture_output=True, check=True)
    return result.stdout


if sys.argv[1] == "snapshot":
    code = f"""import hashlib,json,tarfile
from pathlib import Path
root=Path({APP!r})
files={FILES!r}
archive=Path({(DATA + '/tmp/professional-mode-baseline.tar.gz')!r})
hashes={{}}
with tarfile.open(archive,'w:gz') as tar:
    for name in files:
        path=root/name
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if path.is_file(): tar.add(path,arcname=name)
print(json.dumps(hashes))
"""
    hashes = json.loads(remote(code))
    (OUT / "before.json").write_text(json.dumps(hashes, indent=2))
    subprocess.run(["scp", f"kt-server-208:{DATA}/tmp/professional-mode-baseline.tar.gz", str(OUT / "baseline.tar.gz")], check=True)
    changes = []
    with tarfile.open(OUT / "baseline.tar.gz") as tar:
        for name in FILES:
            if hashes[name] is not None:
                previous = tar.extractfile(name).read().decode("utf-8").replace("\r\n", "\n")
            else:
                previous = ""
            local = (ROOT / name).read_text(encoding="utf-8")
            changes.extend(difflib.unified_diff(previous.splitlines(keepends=True), local.splitlines(keepends=True), fromfile="gpu208/" + name, tofile="local/" + name))
    (OUT / "server-diff.txt").write_text("".join(changes), encoding="utf-8")
    print(json.dumps({"inspected": len(FILES), "new_files": [name for name, value in hashes.items() if value is None], "diff": str(OUT / 'server-diff.txt')}, ensure_ascii=False))
elif sys.argv[1] == "package":
    files = FILES + [str(path.relative_to(ROOT)).replace('\\', '/') for path in (ROOT / "frontend/dist").rglob('*') if path.is_file()]
    checks = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    (OUT / "checksums.json").write_text(json.dumps(checks, indent=2))
    with tarfile.open(OUT / "package.tar.gz", 'w:gz') as tar:
        for name in files: tar.add(ROOT / name, arcname=name)
    print(json.dumps({"packaged_files": len(checks), "package": str(OUT / 'package.tar.gz')}))
elif sys.argv[1] == "status":
    print(remote(f"""import json,sqlite3
from pathlib import Path
counts={{'planned':0,'running':0}}
paths=set(Path({(DATA + '/var')!r}).rglob('*.sqlite3')) | set(Path({(APP + '/backend/data')!r}).glob('*.sqlite3'))
for path in paths:
    connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    try:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='product_analysis_workflows'").fetchone():
            for row in connection.execute('SELECT payload_json FROM product_analysis_workflows'):
                state=json.loads(row[0]).get('status')
                if state in counts: counts[state]+=1
    finally: connection.close()
print(json.dumps(counts))
"""))
elif sys.argv[1] == "sync":
    from datetime import datetime, timedelta, timezone
    name = 'professional-mode-' + datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    target = DATA + '/releases/' + name
    print(remote(f"from pathlib import Path; Path({target!r}).mkdir(parents=True,exist_ok=False); print({target!r})"), flush=True)
    (OUT / 'remote-release.txt').write_text(target)
    for path in [OUT / 'package.tar.gz', OUT / 'checksums.json', OUT / 'before.json', ROOT / 'deploy/professional_mode_install.py', ROOT / 'deploy/professional_mode_live_smoke.py']:
        subprocess.run(['scp', str(path), f'kt-server-208:{target}/{path.name}'], check=True)
    code = f"""import subprocess,os,json
from pathlib import Path
release=Path({target!r})
env={{**os.environ,'TMPDIR':{(DATA + '/tmp')!r}}}
subprocess.run([{PYTHON!r},str(release/'professional_mode_install.py'),'--release',str(release)],check=True,env=env)
test=subprocess.run([{PYTHON!r},'-m','pytest','tests/test_professional_reviews.py','tests/test_workspace_assistant.py','tests/test_analysis_workflow_api.py','tests/test_workspace_lai.py','-q','--tb=short'],cwd={ (APP + '/backend')!r},env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(release/'server-tests.txt').write_text(test.stdout)
print(test.stdout[-1800:],flush=True)
assert test.returncode==0,'Server tests failed; service has not been restarted'
subprocess.run(['systemctl','--user','restart','ktp-backend','ktp-frontend'],check=True)
status=subprocess.run(['systemctl','--user','is-active','ktp-backend','ktp-frontend'],check=True,text=True,stdout=subprocess.PIPE)
print(json.dumps({{'services':status.stdout.splitlines(),'release':str(release)}}),flush=True)
"""
    print(remote(code), flush=True)
else:
    raise ValueError("Use snapshot, package, status or sync")
