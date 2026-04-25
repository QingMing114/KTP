from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAR_DIR = _PROJECT_ROOT / "var"
DATA_DIR = VAR_DIR / "data"
MODELS_DIR = VAR_DIR / "models"
LOGS_DIR = VAR_DIR / "logs"

project_root = _PROJECT_ROOT
var_path = VAR_DIR


def ensure_dirs():
    for d in [VAR_DIR, DATA_DIR, MODELS_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
