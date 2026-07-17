from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "08_runtime"
WORKFLOW_RUNTIME = ROOT / "10_generic_target_workflow" / "runtime"
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(WORKFLOW_RUNTIME))

from deployment_config import load_deployment_config  # noqa: E402
from provenance import collect_provenance  # noqa: E402


def test_stored_deployment_config_contains_no_absolute_paths() -> None:
    raw = json.loads((ROOT / "09_configs" / "deployment_config.json").read_text(encoding="utf-8"))

    def strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [item for child in value.values() for item in strings(child)]
        if isinstance(value, list):
            return [item for child in value for item in strings(child)]
        return []

    path_values = [value for value in strings(raw) if "/" in value or "\\" in value or value == "."]
    assert path_values
    assert all(not Path(value).is_absolute() for value in path_values)


def test_environment_overrides_resolve_paths_at_load_time(tmp_path: Path) -> None:
    project = tmp_path / "deployment"
    config_dir = project / "09_configs"
    config_dir.mkdir(parents=True)
    source = tmp_path / "source"
    source.mkdir()
    raw = {
        "base_dir": ".",
        "source_project_dir": "unused",
        "models": {"model": "Data/model.yml"},
        "audit_outputs": {"audit": "audit/report.md"},
    }
    (config_dir / "deployment_config.json").write_text(json.dumps(raw), encoding="utf-8")

    resolved = load_deployment_config(
        environ={"METATWIN_PROJECT_ROOT": str(project), "METATWIN_SOURCE_PROJECT": str(source)}
    )
    assert Path(resolved["base_dir"]) == project.resolve()
    assert Path(resolved["source_project_dir"]) == source.resolve()
    assert Path(resolved["models"]["model"]) == (source / "Data" / "model.yml").resolve()
    assert Path(resolved["audit_outputs"]["audit"]) == (source / "audit" / "report.md").resolve()


def test_provenance_records_hashes_and_nullable_git_commit(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("stable input\n", encoding="utf-8")
    report = collect_provenance(tmp_path, {"input": source})
    assert report["python"]["version"]
    assert isinstance(report["solvers"], list)
    assert len(report["source_files"][0]["sha256"]) == 64
    assert report["source_files"][0]["file_name"] == "input.txt"
    assert report["git_commit"] is None
