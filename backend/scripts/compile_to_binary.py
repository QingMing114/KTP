"""Compile all Python source files to .so binary extensions using Cython.

Usage:
    python scripts/compile_to_binary.py          # compile in-place
    python scripts/compile_to_binary.py --clean  # remove compiled files
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    "tests", "test", "__pycache__", ".git", ".venv", "venv",
    "node_modules", "data", "plugins", "scripts", "docs", "prompts",
    ".trae", ".mypy_cache", ".pytest_cache", "dist", "build",
    "egg-info",
}

EXCLUDE_FILES = {
    "__init__.py",
    "compile_to_binary.py",
    "license_guard.py",
}

FASTAPI_ROUTE_PATTERNS = [
    "APIRouter",
    "@router.",
    "@app.",
    "fastapi.Header",
    "fastapi.Query",
    "fastapi.Depends",
    "fastapi.Body",
    "fastapi.Form",
    "fastapi.File",
    "fastapi.Cookie",
    "fastapi.Path",
    "from fastapi import",
    "from fastapi.responses import",
]

PYDANTIC_MODEL_PATTERNS = [
    "BaseModel)",
    "BaseSettings)",
    "model_post_init",
    "model_validator",
    "field_validator",
]


def has_fastapi_routes(filepath: Path) -> bool:
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for pattern in FASTAPI_ROUTE_PATTERNS:
        if pattern in content:
            return True
    return False


def has_pydantic_models(filepath: Path) -> bool:
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for pattern in PYDANTIC_MODEL_PATTERNS:
        if pattern in content:
            return True
    return False

INCLUDE_EXTENSIONS = {".py"}


def find_python_packages(root: Path) -> list[Path]:
    packages = []
    for item in sorted(root.iterdir()):
        if item.name.startswith(".") or item.name in EXCLUDE_DIRS:
            continue
        if item.is_dir() and (item / "__init__.py").exists():
            packages.append(item)
    return packages


def find_py_files(package_dir: Path) -> list[Path]:
    py_files = []
    skipped_fastapi = []
    skipped_pydantic = []
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in sorted(files):
            if f in EXCLUDE_FILES:
                continue
            fp = Path(root) / f
            if fp.suffix in INCLUDE_EXTENSIONS:
                if has_fastapi_routes(fp):
                    skipped_fastapi.append(fp.relative_to(ROOT_DIR))
                    continue
                if has_pydantic_models(fp):
                    skipped_pydantic.append(fp.relative_to(ROOT_DIR))
                    continue
                py_files.append(fp)
    if skipped_fastapi:
        print(f"  Skipped {len(skipped_fastapi)} FastAPI route files in {package_dir.name}")
    if skipped_pydantic:
        print(f"  Skipped {len(skipped_pydantic)} Pydantic model files in {package_dir.name}")
    return py_files


def generate_setup(packages: list[Path], output_path: Path) -> str:
    ext_modules = []
    for pkg in packages:
        py_files = find_py_files(pkg)
        for py_file in py_files:
            rel = py_file.relative_to(ROOT_DIR)
            module_name = str(rel.with_suffix("")).replace(os.sep, ".")
            ext_modules.append(f'    Extension("{module_name}", ["{rel}"]),')

    init_files = []
    for pkg in packages:
        init_rel = (pkg / "__init__.py").relative_to(ROOT_DIR)
        init_files.append(f'    ("{init_rel.parent}", ["{init_rel}"]),')

    content = f'''from setuptools import setup
from Cython.Build import cythonize
from setuptools import Extension

ext_modules = [
{chr(10).join(ext_modules)}
]

setup(
    name="ktp_compiled",
    ext_modules=cythonize(
        ext_modules,
        compiler_directives={{
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
        }},
        build_dir="build/cython",
    ),
)
'''
    return content


def compile_sources():
    try:
        from Cython.Build import cythonize
    except ImportError:
        print("ERROR: Cython not installed. Run: pip install cython")
        sys.exit(1)

    packages = find_python_packages(ROOT_DIR)
    if not packages:
        print("No Python packages found")
        return

    print(f"Found {len(packages)} packages to compile:")
    total_files = 0
    for pkg in packages:
        py_files = find_py_files(pkg)
        total_files += len(py_files)
        print(f"  {pkg.name}: {len(py_files)} files")

    print(f"\nTotal: {total_files} files to compile")

    setup_content = generate_setup(packages, ROOT_DIR / "setup_compile.py")
    setup_path = ROOT_DIR / "setup_compile.py"
    setup_path.write_text(setup_content, encoding="utf-8")

    import subprocess
    result = subprocess.run(
        [sys.executable, "setup_compile.py", "build_ext", "--inplace"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Compilation FAILED:")
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        sys.exit(1)

    print("\nCompilation successful!")

    removed = 0
    for pkg in packages:
        py_files = find_py_files(pkg)
        for py_file in py_files:
            if py_file.name == "__init__.py":
                continue
            c_file = py_file.with_suffix(".c")
            if c_file.exists():
                c_file.unlink()
            py_file.unlink()
            removed += 1

    print(f"Removed {removed} .py source files (kept __init__.py)")
    setup_path.unlink(missing_ok=True)
    build_dir = ROOT_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)


def clean_compiled():
    removed_so = 0
    removed_c = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in files:
            fp = Path(root) / f
            if fp.suffix == ".so":
                fp.unlink()
                removed_so += 1
            elif fp.suffix == ".c" and fp.name != "setup_compile.py":
                fp.unlink()
                removed_c += 1

    build_dir = ROOT_DIR / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    print(f"Cleaned: {removed_so} .so files, {removed_c} .c files")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean_compiled()
    else:
        compile_sources()
