import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KTP_ROOT = _PROJECT_ROOT.parent
VAR_DIR = _PROJECT_ROOT / "var"
DATA_DIR = VAR_DIR / "data"
MODELS_DIR = VAR_DIR / "models"
LOGS_DIR = VAR_DIR / "logs"
RUNTIME_DIR = VAR_DIR / "runtime"
REPORTS_DIR = VAR_DIR / "reports"
VISUALIZATIONS_DIR = VAR_DIR / "visualizations"
DEFAULT_LAI_REPORT_DIR = _KTP_ROOT / "reports"

project_root = _PROJECT_ROOT
var_path = VAR_DIR


def get_lai_report_dir(override: str | Path | None = None) -> Path:
    """Resolve the single filesystem directory used for generated LAI reports."""
    configured = (
        override
        or os.environ.get("LAI_REPORT_OUTPUT_DIR")
        or os.environ.get("V2_REPORTS_DIR")
    )
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_LAI_REPORT_DIR.resolve()


def ensure_dirs():
    for d in [
        VAR_DIR,
        DATA_DIR,
        MODELS_DIR,
        LOGS_DIR,
        RUNTIME_DIR,
        REPORTS_DIR,
        VISUALIZATIONS_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
