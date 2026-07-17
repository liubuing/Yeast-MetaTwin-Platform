from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


TRACKED_DISTRIBUTIONS = (
    "cobra",
    "swiglpk",
    "optlang",
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "joblib",
    "python-docx",
    "jsonschema",
    "PyYAML",
    "pytest",
    "torch",
    "transformers",
    "sentencepiece",
    "rdkit",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def collect_provenance(root: Path, source_files: Mapping[str, Path] | None = None) -> dict[str, object]:
    packages: dict[str, str | None] = {}
    for name in TRACKED_DISTRIBUTIONS:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None

    solvers: list[str] = []
    try:
        from cobra.util.solver import solvers as cobra_solvers

        solvers = sorted(cobra_solvers)
    except (ImportError, RuntimeError):
        pass

    sources = []
    for label, path in (source_files or {}).items():
        sources.append(
            {
                "label": label,
                "file_name": path.name,
                "exists": path.is_file(),
                "sha256": _sha256(path) if path.is_file() else None,
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
        )
    return {
        "provenance_version": "1.0",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(), "executable": Path(sys.executable).name},
        "solvers": solvers,
        "dependencies": packages,
        "source_files": sources,
        "git_commit": _git_commit(root),
    }
