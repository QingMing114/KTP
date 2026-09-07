from __future__ import annotations

import py_compile
from pathlib import Path


def test_legacy_spectral_generated_module_is_removed_and_runtime_source_compiles() -> None:
    source_dir = Path(__file__).resolve().parents[1] / "prosail_python"
    assert not (source_dir / "spectral_data_generated.py").exists()
    py_compile.compile(str(source_dir / "spectral_data_full.py"), doraise=True)
    py_compile.compile(str(source_dir / "prospect.py"), doraise=True)
