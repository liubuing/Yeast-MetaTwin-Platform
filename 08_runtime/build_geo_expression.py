from __future__ import annotations

"""Build a real yeast (S. cerevisiae) expression matrix from NCBI GEO.

Downloads a GEO series matrix (microarray) plus the matching platform (GPL)
annotation, maps platform probe IDs to systematic yeast gene names
(YAL001C-style), aggregates replicate probes per gene, filters to the genes
present in the Yeast-MetaTwin model, and writes a genes x conditions CSV that
can be consumed by ``omics_constrain.load_expression_matrix``.

Default dataset: GSE17295 (S. cerevisiae, Affymetrix Yeast Genome 2.0 Array,
GPL2529). Fallbacks: GSE162513, GSE210964 (both GPL2529 yeast datasets).

Usage (working dir = 08_runtime/):
    python build_geo_expression.py
    python build_geo_expression.py --gse GSE162513
"""

import argparse
import gzip
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATABASES_DIR = ROOT / "01_databases"
MODELS_DIR = ROOT / "03_models"
CACHE_DIR = Path(__file__).resolve().parent / "geo_cache"

GEO_FTP = "https://ftp.ncbi.nlm.nih.gov/geo"

# Systematic S. cerevisiae nuclear gene name, e.g. YAL001C / YBR002W.
SYS_NUCLEAR = re.compile(r"^Y[A-P][LR]\d{3}[WC]$")
# Mitochondrial gene names used in the model, e.g. Q0045, Q0275.
MITO = re.compile(r"^Q\d{3}$")


def is_yeast_gene(name: str) -> bool:
    return bool(SYS_NUCLEAR.match(name) or MITO.match(name))


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _series_matrix_url(gse: str) -> str:
    bucket = gse[:-3] + "nnn"
    return f"{GEO_FTP}/series/{bucket}/{gse}/matrix/{gse}_series_matrix.txt.gz"


def _gpl_soft_url(gpl: str) -> str:
    num = int(re.sub(r"\D", "", gpl))
    bucket = gpl[:-3] + "nnn"
    return f"{GEO_FTP}/platforms/{bucket}/{gpl}/soft/{gpl}_family.soft.gz"


def stream_download(url: str, dest: Path, tries: int = 6, timeout: int = 60) -> Path:
    """Download ``url`` to ``dest`` in chunks with retries. Skips if cached."""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [cache] {dest.name} ({dest.stat().st_size} bytes)")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            total = 0
            t0 = time.time()
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    fh.write(chunk)
                    total += len(chunk)
            tmp.replace(dest)
            print(f"  [download] {dest.name}: {total} bytes in {time.time()-t0:.1f}s "
                  f"(attempt {attempt})")
            return dest
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  [download] attempt {attempt}/{tries} failed for {url}: "
                  f"{exc!r}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            time.sleep(2 * attempt)
    raise RuntimeError(f"Failed to download {url}: {last_err}")


def read_gz_text(path: Path) -> str:
    """Read a gzipped text file, tolerating truncated/partial downloads.

    A normal gzip read is attempted first. If the archive is incomplete
    (e.g. an interrupted cache download), fall back to block-wise zlib
    decompression and return whatever complete content is recoverable.
    """
    raw = path.read_bytes()
    try:
        return gzip.decompress(raw).decode("utf-8", errors="ignore")
    except (OSError, EOFError, gzip.BadGzipFile):
        pass

    import zlib
    dec = zlib.decompressobj(zlib.MAX_WBITS | 16)
    chunks: list[bytes] = []
    try:
        chunks.append(dec.decompress(raw))
        chunks.append(dec.flush())
    except zlib.error:
        pass  # Keep whatever decompressed cleanly before the truncation.
    out = b"".join(chunks)
    print(f"  [warn] {path.name} appears truncated; recovered "
          f"{len(out)} bytes of decompressed content.", file=sys.stderr)
    return out.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Platform (GPL) parsing: probe ID -> systematic gene name
# ---------------------------------------------------------------------------

# Probe identifiers across GEO platforms are short tokens (e.g. Affymetrix
# "1769308_at", Agilent "A_23_P117082"). Used to discard garbage fragment lines
# that can appear when decompressing a truncated cache file.
PROBE_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")


def parse_gpl_probe_to_gene(gpl_text: str) -> dict[str, str]:
    """Parse a GPL family SOFT table into a probe_id -> systematic_name map.

    Robust to truncated files: rows are pre-filtered to a sane probe-ID format
    and the expected column count. The systematic-name column is taken from an
    "ORF" column when present, otherwise auto-detected as the column with the
    most systematic yeast-gene values.
    """
    lines = gpl_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.startswith("!platform_table_begin"))
    except StopIteration:
        raise RuntimeError("GPL file has no !platform_table_begin section")

    header = lines[start + 1].split("\t")
    n_cols = len(header)
    col_idx = {name: i for i, name in enumerate(header)}
    if "ID" not in col_idx:
        raise RuntimeError(f"GPL table missing ID column. Header: {header}")
    id_idx = col_idx["ID"]

    # Keep only well-formed data rows: full column count + plausible probe ID.
    rows: list[list[str]] = []
    for ln in lines[start + 2:]:
        if ln.startswith("!") or ln.startswith("^"):
            break
        if not ln.strip():
            continue
        parts = ln.split("\t")
        if len(parts) != n_cols:
            continue
        probe = parts[id_idx].strip()
        if not PROBE_RE.match(probe):
            continue
        rows.append(parts)

    print(f"  [gpl] well-formed probe rows: {len(rows)} (of {n_cols} columns)")

    # Fast path: an explicit ORF / systematic-name column.
    orf_col = -1
    for name, idx in col_idx.items():
        if idx == id_idx:
            continue
        low = name.lower().replace(" ", "").replace("_", "")
        if low in ("orf", "systematicname", "systematicname"):
            orf_col = idx
            break

    if orf_col >= 0:
        best_col, best_hits = orf_col, sum(
            1 for r in rows if is_yeast_gene(r[orf_col].strip()))
    else:
        # Auto-detect: column with the most systematic yeast-gene values.
        best_col, best_hits = -1, 0
        for idx in range(n_cols):
            if idx == id_idx:
                continue
            hits = sum(1 for r in rows if is_yeast_gene(r[idx].strip()))
            if hits > best_hits:
                best_hits, best_col = hits, idx

    if best_col < 0 or best_hits == 0:
        raise RuntimeError(
            "Could not locate a systematic-name column in GPL table. "
            f"Header: {header}"
        )

    print(f"  [gpl] systematic-name column = '{header[best_col]}' "
          f"({best_hits} probe rows map to yeast genes)")

    probe_to_gene: dict[str, str] = {}
    for r in rows:
        gene = r[best_col].strip()
        probe = r[id_idx].strip()
        if gene and is_yeast_gene(gene):
            probe_to_gene.setdefault(probe, gene)
    return probe_to_gene


# ---------------------------------------------------------------------------
# Series matrix parsing
# ---------------------------------------------------------------------------

def parse_series_matrix(sm_text: str) -> tuple[list[str], list[str], list[list[str]]]:
    """Return (sample_columns, condition_labels, value_rows[probe][samples]).

    value_rows is a list of [probe_id, v1, v2, ...] string rows.
    """
    lines = sm_text.splitlines()

    # Condition labels: prefer sample source names, fall back to titles, then
    # geo accessions.
    def grab_all(key: str) -> list[str]:
        for ln in lines:
            if ln.startswith(key + "\t"):
                parts = ln.split("\t")[1:]
                return [p.strip().strip('"') for p in parts]
        return []

    titles = grab_all("!Sample_title")
    sources = grab_all("!Sample_source_name_ch1")
    accessions = grab_all("!Sample_geo_accession")

    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.startswith("!series_matrix_table_begin"))
        end = next(i for i, ln in enumerate(lines)
                   if ln.startswith("!series_matrix_table_end"))
    except StopIteration:
        raise RuntimeError("Series matrix table section not found")

    header = lines[start + 1].split("\t")
    header = [h.strip().strip('"') for h in header]
    # First column is ID_REF (probe id); remaining are sample value columns.
    sample_columns = header[1:]
    n_samples = len(sample_columns)

    # Build condition labels (unique). Prefer the most informative field:
    # source names are often uniform (e.g. all "yeast cell culture") while
    # sample titles carry the real condition/strain identifiers. Pick whichever
    # of sources/titles has more distinct values.
    candidates = [
        c for c in (sources, titles)
        if c and len(c) == n_samples
    ]
    if candidates:
        base = max(candidates, key=lambda c: len(set(c)))
    elif len(accessions) == n_samples:
        base = accessions
    else:
        base = []
    if not base:
        base = [f"sample_{i+1}" for i in range(n_samples)]

    labels: list[str] = []
    seen: dict[str, int] = {}
    for i, raw in enumerate(base):
        lbl = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_") or f"sample_{i+1}"
        if lbl in seen:
            seen[lbl] += 1
            lbl = f"{lbl}_{seen[lbl]}"
        else:
            seen[lbl] = 1
        labels.append(lbl)

    value_rows: list[list[str]] = []
    for ln in lines[start + 2:end]:
        if not ln.strip():
            continue
        parts = ln.split("\t")
        probe = parts[0].strip().strip('"')
        vals = [p.strip().strip('"') for p in parts[1:]]
        # Pad/truncate to n_samples.
        if len(vals) < n_samples:
            vals += [""] * (n_samples - len(vals))
        value_rows.append([probe] + vals[:n_samples])

    return sample_columns, labels, value_rows


# ---------------------------------------------------------------------------
# Matrix assembly
# ---------------------------------------------------------------------------

def build_expression_matrix(
    probe_to_gene: dict[str, str],
    value_rows: list[list[str]],
    labels: list[str],
    model_genes: set[str],
) -> tuple[list[str], np.ndarray, dict[str, int]]:
    """Aggregate probe values per gene (mean) and filter to model genes."""
    n_cond = len(labels)

    # Accumulate per-gene value lists.
    gene_acc: dict[str, list[list[float]]] = {}
    probe_used = 0
    probe_missing = 0
    for row in value_rows:
        probe = row[0]
        gene = probe_to_gene.get(probe)
        if not gene:
            probe_missing += 1
            continue
        if gene not in model_genes:
            continue
        vals: list[float] = []
        for v in row[1:]:
            try:
                fv = float(v)
            except (ValueError, TypeError):
                fv = np.nan
            vals.append(fv)
        if len(vals) != n_cond:
            continue
        gene_acc.setdefault(gene, []).append(vals)
        probe_used += 1

    # Mean across probes (ignoring NaNs); drop genes that are all-NaN.
    gene_ids: list[str] = []
    matrix_rows: list[list[float]] = []
    for gene in sorted(gene_acc):
        arr = np.array(gene_acc[gene], dtype=np.float64)
        with np.errstate(all="ignore"):
            means = np.nanmean(arr, axis=0)
        if np.all(np.isnan(means)):
            continue
        # Replace any remaining NaN (a condition all-NaN across probes) with 0.
        means = np.where(np.isnan(means), 0.0, means)
        gene_ids.append(gene)
        matrix_rows.append(means.tolist())

    stats = {
        "probes_used": probe_used,
        "probes_no_gene_map": probe_missing,
        "genes_with_data": len(gene_ids),
    }
    matrix = np.array(matrix_rows, dtype=np.float64)
    return gene_ids, matrix, stats


def load_model_genes() -> list[str]:
    import cobra
    model_path = MODELS_DIR / "gems" / "Yeast-MetaTwin.yml"
    model = cobra.io.load_yaml_model(str(model_path))
    return [g.id for g in model.genes]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEFAULT_GSE = ["GSE17295", "GSE162513", "GSE210964"]
DEFAULT_GPL = "GPL2529"


def run(gse_list: list[str], gpl: str, output: Path) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading Yeast-MetaTwin model gene IDs...")
    model_genes_list = load_model_genes()
    model_genes = set(model_genes_list)
    print(f"  Model genes: {len(model_genes)}")

    print(f"Downloading/parsing platform {gpl} annotation...")
    gpl_path = stream_download(_gpl_soft_url(gpl), CACHE_DIR / f"{gpl}_family.soft.gz")
    probe_to_gene = parse_gpl_probe_to_gene(read_gz_text(gpl_path))
    print(f"  Probe -> gene map: {len(probe_to_gene)} probes")
    mapped_model = {g for g in probe_to_gene.values() if g in model_genes}
    print(f"  Platform covers {len(mapped_model)}/{len(model_genes)} model genes")

    last_err: Exception | None = None
    for gse in gse_list:
        print(f"\nTrying series {gse}...")
        try:
            sm_path = stream_download(_series_matrix_url(gse),
                                      CACHE_DIR / f"{gse}_series_matrix.txt.gz")
            _, labels, value_rows = parse_series_matrix(read_gz_text(sm_path))
            if len(labels) < 3:
                raise RuntimeError(f"Too few conditions ({len(labels)}) in {gse}")
            print(f"  Samples/conditions: {len(labels)} | probe rows: {len(value_rows)}")

            gene_ids, matrix, stats = build_expression_matrix(
                probe_to_gene, value_rows, labels, model_genes
            )
            if stats["genes_with_data"] == 0:
                raise RuntimeError("No model genes matched expression data")

            # Write CSV.
            output.parent.mkdir(parents=True, exist_ok=True)
            header = ["gene_id"] + labels
            with open(output, "w", encoding="utf-8", newline="") as fh:
                fh.write(",".join(header) + "\n")
                for i, gene in enumerate(gene_ids):
                    vals = ",".join(f"{v:.4f}" for v in matrix[i])
                    fh.write(f"{gene},{vals}\n")

            coverage = 100.0 * stats["genes_with_data"] / len(model_genes)
            print("\n=== SUCCESS ===")
            print(f"  Series:            {gse} ({gpl})")
            print(f"  Output:            {output}")
            print(f"  Genes with data:   {stats['genes_with_data']}/{len(model_genes)} "
                  f"({coverage:.1f}% model coverage)")
            print(f"  Conditions:        {len(labels)}")
            print(f"  Probes used:       {stats['probes_used']} "
                  f"(unmapped probes: {stats['probes_no_gene_map']})")
            print(f"  Condition labels:  {labels[:8]}"
                  f"{' ...' if len(labels) > 8 else ''}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"  [skip] {gse} failed: {exc!r}", file=sys.stderr)
            continue

    print(f"ERROR: all series failed. Last error: {last_err!r}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a real yeast GEO expression matrix for the "
                    "Yeast-MetaTwin model.",
    )
    parser.add_argument("--gse", type=str, default=None,
                        help="GEO series accession (default: try GSE17295, "
                             "then GSE162513, GSE210964).")
    parser.add_argument("--gpl", type=str, default=DEFAULT_GPL,
                        help="GEO platform accession (default: GPL2529).")
    parser.add_argument("--output", type=Path,
                        default=DATABASES_DIR / "geo_yeast_expression_real.csv",
                        help="Output CSV path.")
    args = parser.parse_args()

    socket.setdefaulttimeout(60)
    gse_list = [args.gse] if args.gse else DEFAULT_GSE
    return run(gse_list, args.gpl, args.output)


if __name__ == "__main__":
    sys.exit(main())
