# Run Artifact Layout

Runs belong under `runs/<run-id>/` or the directory selected by `METATWIN_RUNS_DIR`:

```text
runs/<run-id>/
  environment.json   OS, Python, solver, dependencies, source hashes, Git commit
  state.json         stage status and timestamps
  events.jsonl       append-only stage events
  manifest.json      artifact hashes and run outcome
  inputs/            immutable copied or referenced input manifests
  outputs/           machine-readable results
  reports/           human-readable summaries
  logs/              tool stdout/stderr when needed
```

Run directories are ignored by Git. A run is reproducible only when its configuration hash, source/model hashes, dependency versions, asset checksums, and random seeds are present. Do not place canonical datasets, trained models, or hand-curated source tables under a run directory. Promote reviewed outputs through a separate, documented process and retain the originating run ID.
