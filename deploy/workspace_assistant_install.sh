set -euo pipefail
base=/data/yuehao/apps/ktp
app="$base/app"
stage="$base/releases/workspace-assistant-20261012"
mkdir -p "$stage"
tar -xzf "$base/workspace-assistant-20261012.tar.gz" -C "$stage"
/data/yuehao/conda-envs/ktp-prod/bin/python - "$app" "$stage" <<'PY'
import sys,json,shutil,py_compile
from pathlib import Path
app,stage=map(Path,sys.argv[1:])
files=json.loads((stage/'release-files.json').read_text())
for f in files:
    if f.endswith('.py'):
        py_compile.compile(str(stage/f),doraise=True)
backup=stage/'backup'
backup.mkdir(exist_ok=False)
for f in files:
    dst=app/f
    if dst.exists():
        saved=backup/f
        saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(dst,saved)
shutil.copytree(app/'frontend/dist',backup/'dist')
for f in files:
    dst=app/f
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(stage/f,dst)
previous=stage/'previous-dist'
(app/'frontend/dist').rename(previous)
shutil.copytree(stage/'frontend/dist',app/'frontend/dist')
for asset in (previous/'assets').rglob('*'):
    if asset.is_file():
        target=app/'frontend/dist/assets'/asset.relative_to(previous/'assets')
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(asset,target)
print('Installed',len(files),'source files and frontend dist; backup:',backup)
PY
