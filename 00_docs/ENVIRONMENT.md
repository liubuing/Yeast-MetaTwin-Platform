# Environment Setup

The deployment is a research snapshot, not a single all-plugin environment. Use Python 3.11 or newer for the main environment; CI uses Python 3.12. Install the complete main stack with:

```text
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

On POSIX systems, use `.venv/bin/python`. The requirement layers are:

| File | Scope |
|---|---|
| `requirements-core.txt` | tabular processing and report output |
| `requirements-fba.txt` | COBRApy, GLPK, model YAML loading |
| `requirements-ml.txt` | reaction-evidence training and serialized model validation |
| `requirements-generic.txt` | generic workflow schema validation |
| `requirements-dev.txt` | complete main stack plus tests |
| `constraints.txt` | exact main-environment versions |

## Plugin Isolation

UniKP serialized estimators require scikit-learn 1.2.x and NumPy 1.x. Create a separate Python 3.10 environment and install `requirements-plugin-unikp.txt`. Do not install it into the main environment. The lock file is a compatibility target and still requires a smoke test on each supported OS.

CLEAN is not declared installable in either environment because its adapter/checkpoints are incomplete. DLKcat uses `04_prediction_plugins/DLKcat/.venv` with `requirements-dlkcat.txt`; run `benchmark.py` from the deployment root to verify the fixed smoke and upstream public examples. On Windows, the adapter imports PyTorch before NumPy/RDKit to avoid the recorded `c10.dll` initialization conflict.

## Configuration

Stored configuration is portable. Relative `base_dir` is resolved against the project root; `source_project_dir` is resolved against `base_dir`; model and audit paths are resolved against the source project.

| Variable | Effect |
|---|---|
| `METATWIN_PROJECT_ROOT` | deployment root and default config location |
| `METATWIN_SOURCE_PROJECT` | external Yeast-MetaTwin source checkout |
| `METATWIN_CONFIG` | alternate deployment JSON |
| `METATWIN_RUNS_DIR` | generic workflow run storage |
| `METATWIN_MMSEQS` | MMseqs2 executable when it is not on `PATH` |

Run `python 08_runtime/environment_check.py --verify-assets` before model or plugin execution. Add `--output runs/<run-id>/environment.json` to retain a standalone report.
