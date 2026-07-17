# Phase 1 Scope

Phase 1 deploys the reliable model-query core of the integrated Yeast-MetaTwin platform.

## Included

- Load `yeast-GEM.yml` and `Yeast-MetaTwin.yml` from the existing Yeast-MetaTwin project.
- Verify model sizes, solver status, objective values, and `rxn*` underground reaction counts.
- Check that existing pathway audit outputs are available.
- Produce a machine-readable and human-readable deployment verification report.

## Not Included Yet

- Training new ML models.
- Running CLEAN, DeepECtransformer, UniKP, DLKcat, ESP, ProSmith, EnzRank, or P450 predictors.
- Downloading and normalizing all external databases.
- Adding new reactions to Yeast-MetaTwin.

These are Phase 2/3 tasks after database normalization, leakage checks, and plugin interfaces are stable.
