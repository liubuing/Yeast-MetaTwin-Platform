from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = ROOT.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from plugin_runtime.dlkcat import predict
from plugin_runtime.schema import PluginInput, RunStatus


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DLKcat fixed smoke and official public example benchmark.")
    parser.add_argument("--report", type=Path, default=ROOT / "benchmark_report.json")
    args = parser.parse_args()
    example_dir = ROOT / "DeeplearningApproach" / "Code" / "example"
    with (example_dir / "input.tsv").open(encoding="utf-8", newline="") as handle:
        inputs = list(csv.DictReader(handle, delimiter="\t"))
    with (example_dir / "output.tsv").open(encoding="utf-8", newline="") as handle:
        expected = list(csv.DictReader(handle, delimiter="\t"))

    rows = []
    for index, (input_row, expected_row) in enumerate(zip(inputs, expected, strict=True), start=1):
        result = predict(PluginInput(
            request_id=f"official-example-{index}",
            capability="kcat_prediction",
            sequence=input_row["Protein Sequence"],
            substrate_smiles=input_row["Substrate SMILES"],
        ), PLUGIN_ROOT)
        observed = next((item.value for item in result.predictions if item.name == "kcat"), None)
        target = float(expected_row["Kcat value (1/s)"])
        rows.append({"request_id": result.request_id, "status": result.status.value, "expected_kcat_s-1": target, "observed_kcat_s-1": observed, "absolute_error": None if observed is None else abs(observed - target)})

    fixed = predict(PluginInput(request_id="smoke-dlkcat-001", capability="kcat_prediction", sequence="MKTAYIAKQRQISFVKSHFSRQ", substrate_smiles="CC(=O)O"), PLUGIN_ROOT)
    passed = fixed.status == RunStatus.READY and all(row["status"] == "ready" and row["absolute_error"] <= 0.00005 for row in rows)
    report = {
        "status": "ready" if passed else "blocked",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": sys.version, "executable": sys.executable},
        "fixed_smoke": fixed.to_dict(),
        "public_benchmark": {
            "name": "DLKcat upstream Code/example",
            "version": "commit-7c15d0d4a7ac029f9d75564d9f2a93874aeaaec7",
            "input_sha256": file_sha256(example_dir / "input.tsv"),
            "expected_output_sha256": file_sha256(example_dir / "output.tsv"),
            "tolerance_kcat_s-1": 0.00005,
            "rows": rows,
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
