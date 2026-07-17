from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "06_evaluation"

SOURCES = [
    {"plugin": "CLEAN", "source_type": "paper_repo", "url": "https://github.com/tttianhao/CLEAN"},
    {"plugin": "CLEAN", "source_type": "paper", "url": "https://www.science.org/doi/10.1126/science.adf2465"},
    {"plugin": "UniKP", "source_type": "paper_repo", "url": "https://github.com/Luo-SynBioLab/UniKP"},
    {"plugin": "UniKP", "source_type": "paper", "url": "https://pubs.acs.org/doi/10.1021/acs.jcim.3c00765"},
    {"plugin": "DLKcat", "source_type": "paper_repo", "url": "https://github.com/SysBioChalmers/DLKcat"},
    {"plugin": "DLKcat", "source_type": "paper", "url": "https://www.nature.com/articles/s41467-022-33113-0"},
]


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Yeast-MetaTwin asset recovery audit"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read(200000).decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def classify(text: str) -> dict[str, Any]:
    low = text.lower()
    keywords = ["pretrained", "checkpoint", "google drive", "zenodo", "figshare", "download", "model", "data", "pth", "pkl", "xlsx"]
    hits = [kw for kw in keywords if kw in low]
    if any(kw in low for kw in ["google drive", "zenodo", "figshare"]):
        status = "download_source_likely_documented"
    elif any(kw in low for kw in ["pretrained", "checkpoint", "download", "data"]):
        status = "documentation_or_assets_mentioned_review_required"
    else:
        status = "source_reachable_no_asset_instruction_detected"
    return {"recovery_source_status": status, "detected_keywords": "|".join(hits)}


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 Plugin Asset Recovery Sources",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Source Status",
        "",
        "| Plugin | Source | HTTP | Recovery status | Keywords |",
        "|---|---|---:|---|---|",
    ]
    for row in payload["sources"]:
        lines.append(f"| {row['plugin']} | {row['url']} | {row['http_status']} | {row['recovery_source_status']} | {row['detected_keywords']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This audit records where plugin assets may be recoverable from. It does not mark assets as present unless files exist locally under the expected deployment paths. Manual download or license review may still be required.",
            "",
            "## Output",
            "",
            "- `06_evaluation/phase2_plugin_asset_recovery_sources.csv`",
            "- `06_evaluation/phase2_plugin_asset_recovery_sources.json`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = []
    for item in SOURCES:
        status, text = fetch(item["url"])
        classification = classify(text) if status else {"recovery_source_status": "source_unreachable", "detected_keywords": ""}
        rows.append({**item, "http_status": status, **classification, "content_sample": text[:1000].replace("\r", " ").replace("\n", " ")})
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "sources": rows}
    write_csv(EVAL_DIR / "phase2_plugin_asset_recovery_sources.csv", rows, list(rows[0].keys()))
    (EVAL_DIR / "phase2_plugin_asset_recovery_sources.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (EVAL_DIR / "phase2_plugin_asset_recovery_sources.md").write_text(render_report(payload), encoding="utf-8")
    print(EVAL_DIR / "phase2_plugin_asset_recovery_sources.md")


if __name__ == "__main__":
    main()
