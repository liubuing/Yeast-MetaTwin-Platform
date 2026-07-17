from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


FILE_ID = "1kwYd4VtzYuMvJMWXy6Vks91DSUAOcKpZ"
LANDING_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
ROOT = Path(__file__).resolve().parent
DOWNLOAD_DIR = ROOT / "downloads"
ARCHIVE = DOWNLOAD_DIR / "pretrained.zip"
RESULT = DOWNLOAD_DIR / "last_download_result.json"
PIN = DOWNLOAD_DIR / "pretrained.zip.sha256"
PRETRAINED_DIR = ROOT / "data" / "pretrained"
REQUIRED_ARCHIVE_BASENAMES = {"split100.pth", "100.pt"}
ALLOWED_SUFFIXES = {".pt", ".pth", ".pkl"}


class DownloadFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.inputs: dict[str, str] = {}
        self._in_download_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "download-form":
            self._in_download_form = True
            self.action = values.get("action")
        elif tag == "input" and self._in_download_form:
            name, value = values.get("name"), values.get("value")
            if name and value is not None:
                self.inputs[name] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._in_download_form = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_result(status: str, **details: object) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "official_file_id": FILE_ID,
        "official_landing_url": LANDING_URL,
        **details,
    }
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def open_download(opener: urllib.request.OpenerDirector, timeout: int):
    first = opener.open(LANDING_URL, timeout=timeout)
    content_type = first.headers.get_content_type()
    if content_type != "text/html":
        return first

    page = first.read(1024 * 1024).decode("utf-8", errors="replace")
    parser = DownloadFormParser()
    parser.feed(page)
    if not parser.action or not parser.inputs:
        raise RuntimeError("Google Drive returned HTML without a recognized download confirmation form")
    confirmed_url = parser.action + "?" + urllib.parse.urlencode(parser.inputs)
    return opener.open(confirmed_url, timeout=timeout)


def download(timeout: int, retries: int) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    partial = ARCHIVE.with_suffix(".zip.part")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", "CLEAN-official-asset-recovery/1.0")]
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            with open_download(opener, timeout) as response, partial.open("wb") as output:
                if response.headers.get_content_type() == "text/html":
                    prefix = response.read(4096)
                    raise RuntimeError(f"confirmation produced HTML instead of ZIP: {prefix[:120]!r}")
                shutil.copyfileobj(response, output, length=1024 * 1024)
            if partial.stat().st_size < 100_000_000:
                raise RuntimeError(f"download too small for advertised 141M archive: {partial.stat().st_size} bytes")
            if not zipfile.is_zipfile(partial):
                raise RuntimeError("download is not a valid ZIP archive")
            partial.replace(ARCHIVE)
            return ARCHIVE
        except Exception as exc:
            errors.append(f"attempt {attempt}/{retries}: {type(exc).__name__}: {exc}")
            partial.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(5 * attempt, 15))
    raise RuntimeError(" | ".join(errors))


def verify_and_install(archive: Path, expected_sha256: str | None) -> dict[str, object]:
    observed = sha256_file(archive)
    pinned = expected_sha256
    if not pinned and PIN.is_file():
        pinned = PIN.read_text(encoding="ascii").split()[0]
    if pinned and observed.lower() != pinned.lower():
        raise RuntimeError(f"SHA256 mismatch: expected {pinned.lower()}, observed {observed.lower()}")

    with zipfile.ZipFile(archive) as bundle:
        files = [item for item in bundle.infolist() if not item.is_dir()]
        by_basename = {Path(item.filename).name: item for item in files}
        missing = sorted(REQUIRED_ARCHIVE_BASENAMES - by_basename.keys())
        if missing:
            raise RuntimeError("official archive lacks required files: " + ", ".join(missing))
        selected = [item for item in files if Path(item.filename).suffix.lower() in ALLOWED_SUFFIXES]
        if len({Path(item.filename).name for item in selected}) != len(selected):
            raise RuntimeError("archive contains duplicate model basenames; refusing ambiguous extraction")
        PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
        installed = []
        for item in selected:
            target = PRETRAINED_DIR / Path(item.filename).name
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            installed.append({"path": str(target.relative_to(ROOT)), "size_bytes": target.stat().st_size, "sha256": sha256_file(target)})
    if not PIN.exists():
        PIN.write_text(f"{observed}  pretrained.zip\n", encoding="ascii")
    return {"archive_size_bytes": archive.stat().st_size, "archive_sha256": observed, "installed": installed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry the official CLEAN pretrained.zip download and install verified members.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--expected-sha256", help="trusted operator-supplied hash; upstream does not publish one")
    parser.add_argument("--archive", type=Path, help="verify/install an already downloaded official archive")
    args = parser.parse_args()
    try:
        archive = args.archive.resolve() if args.archive else download(args.timeout, args.retries)
        details = verify_and_install(archive, args.expected_sha256)
        write_result("downloaded_and_installed", **details)
        print(json.dumps(details, indent=2))
        return 0
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        write_result("blocked", error=error)
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
