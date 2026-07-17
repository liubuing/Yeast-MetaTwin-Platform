# DLKcat deployment snapshot

Status: **ready** for isolated CPU inference on the validated Windows host.

The inference source, dictionaries, example data, and checkpoint are verbatim assets from official DLKcat commit `7c15d0d4a7ac029f9d75564d9f2a93874aeaaec7`. The checkpoint is installed as `DeeplearningApproach/Results/output/saved_model` because its upstream 151-character filename exceeds the Win32 path limit under this deployment root. Its bytes and SHA256 are unchanged.

## Verify

Run from the deployment root:

```text
04_prediction_plugins\DLKcat\.venv\Scripts\python.exe 04_prediction_plugins\DLKcat\benchmark.py
```

The command runs one fixed smoke input and compares all three official `Code/example` rows against the published output. `benchmark_report.json` is the retained result. The integrated entrypoint is `plugin_runtime.dlkcat:predict`.

To recover missing or changed assets from the pinned official Git repository:

```text
04_prediction_plugins\DLKcat\.venv\Scripts\python.exe 04_prediction_plugins\DLKcat\download_dlkcat.py
```

Use `--force` to replace assets even when their current hashes match. Every downloaded file is checked against `source_manifest.json` before installation.

## Trust and limits

DLKcat is GPL-3.0-only; the verbatim upstream license is `LICENSE.upstream.md`. The official preprocessing dictionaries are pickle files and must be treated as trusted serialized assets from the pinned repository, not as safe inputs from arbitrary sources. The model provides point estimates without calibrated uncertainty or a deployed out-of-domain detector. Inference results are prioritization evidence, not curated kinetic evidence.

The verbatim upstream CLI remains for provenance. Use the integrated entrypoint on Windows because the upstream CLI hard-codes the original overlong checkpoint filename.
