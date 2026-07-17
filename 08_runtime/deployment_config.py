from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigError(ValueError):
    pass


def _resolve(value: str, base: Path) -> str:
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return str((path if path.is_absolute() else base / path).resolve())


def load_deployment_config(
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    project_root = Path(env.get("METATWIN_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)).expanduser().resolve()
    selected = config_path or Path(env.get("METATWIN_CONFIG", project_root / "09_configs" / "deployment_config.json"))
    selected = selected.expanduser().resolve()
    try:
        config = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentConfigError(f"cannot read deployment config {selected}: {exc}") from exc
    if not isinstance(config, dict):
        raise DeploymentConfigError(f"deployment config must contain a JSON object: {selected}")

    base_dir = Path(_resolve(str(config.get("base_dir", ".")), project_root))
    source_value = env.get("METATWIN_SOURCE_PROJECT", config.get("source_project_dir"))
    if not source_value:
        raise DeploymentConfigError("source_project_dir or METATWIN_SOURCE_PROJECT is required")
    source_project = Path(_resolve(str(source_value), base_dir))

    resolved = dict(config)
    resolved["base_dir"] = str(base_dir)
    resolved["source_project_dir"] = str(source_project)
    resolved["models"] = {
        name: _resolve(str(path), source_project) for name, path in config.get("models", {}).items()
    }
    resolved["audit_outputs"] = {
        name: _resolve(str(path), source_project) for name, path in config.get("audit_outputs", {}).items()
    }
    resolved["config_path"] = str(selected)
    return resolved
