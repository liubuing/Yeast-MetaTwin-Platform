# CLEAN Asset Recovery

Status: **blocked**. The official pretrained archive is not present, so no inference smoke was run.

## Retry

From this directory, use a Python 3.10 environment:

```text
python retry_download_assets.py --timeout 120 --retries 5
```

The downloader follows the current Google Drive confirmation form, rejects HTML/small/non-ZIP responses, requires `split100.pth` and `100.pt`, computes SHA256 for the archive and each installed file, and writes `downloads/last_download_result.json`. Upstream does not publish an archive checksum. On first success the computed digest is pinned in `downloads/pretrained.zip.sha256`; for stronger first-acquisition control, supply a digest obtained through a separately trusted channel with `--expected-sha256`.

An operator-downloaded official archive can be checked without network access:

```text
python retry_download_assets.py --archive C:\path\to\pretrained.zip --expected-sha256 <trusted-sha256>
```

## Isolated Environment

Do not install CLEAN into the deployment's main or UniKP environment. The official paper setup is Python 3.10.4, PyTorch 1.11.0, CUDA 11.3, and fair-esm 1.0.2; the current official requirements file instead pins fair-esm 2.0.0. `requirements-clean.txt` mirrors the current official repository. Create an isolated environment and validate the exact CPU/GPU PyTorch build on the target OS before inference.

The sibling Yeast-MetaTwin checkout contains source files whose Git blobs exactly match official CLEAN `main`, `split100.csv`, and both ESM-1b files. They are inventoried in `asset_manifest.json`; they do not replace the missing CLEAN checkpoint and cluster-center embedding.

## License

The current repository contains a CLEAN-specific non-exclusive research-use license PDF, while GitHub's repository metadata reports MIT and its license endpoint returns 404. Treat the specific research-use license as controlling and require manual review before redistribution or commercial use.

## Smoke Gate

The fixed input is `smoke/fixed_input.fasta`. Do not mark readiness ready until all official assets have hashes recorded, the isolated environment loads the checkpoint and ESM model, and this exact input produces a non-empty EC prediction. Current machine-readable status is `readiness.json` with `status: blocked`.
