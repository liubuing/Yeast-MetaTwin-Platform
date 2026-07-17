from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "source_manifest.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover pinned official DLKcat inference assets.")
    parser.add_argument("--force", action="store_true", help="replace already valid files")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commit = manifest["upstream"]["commit"]

    with tempfile.TemporaryDirectory(prefix="dlkcat-download-") as temp_dir:
        checkout = Path(temp_dir) / "DLKcat"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", manifest["upstream"]["repository"], str(checkout)],
            check=True,
        )
        subprocess.run(["git", "-C", str(checkout), "config", "core.longpaths", "true"], check=True)

        for asset in manifest["assets"]:
            destination = ROOT / asset["installed_path"]
            if destination.is_file() and not args.force and sha256(destination.read_bytes()) == asset["sha256"]:
                continue
            data = subprocess.check_output(["git", "-C", str(checkout), "show", f"{commit}:{asset['source_path']}"])
            observed = sha256(data)
            if observed != asset["sha256"] or len(data) != asset["size"]:
                raise RuntimeError(f"source verification failed for {asset['source_path']}: sha256={observed}, size={len(data)}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

    archive = ROOT / "DeeplearningApproach" / "Data" / "input.zip"
    input_dir = archive.parent / "input"
    if input_dir.exists():
        shutil.rmtree(input_dir)
    with zipfile.ZipFile(archive) as handle:
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in handle.namelist()):
            raise RuntimeError("unsafe member in official input.zip")
        handle.extractall(archive.parent)
    print(f"Recovered and verified DLKcat commit {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
