# Universal Model Boundaries

The generic workflow is a prioritization system, not a single biochemical truth model.

## Reusable Core Layers

| Layer | Reusable Across Targets | Output | Validation Boundary |
|---|---:|---|---|
| Target identity normalization | Yes | compound aliases, formulas, IDs, structures | Identity confidence only |
| Candidate reaction declaration | Yes | reaction hypotheses and route definitions | Hypothesis unless curated evidence exists |
| Model/FBA feasibility | Yes | precursor and demand feasibility | Model feasibility, not enzyme proof |
| Reaction evidence ML/PU | Yes | reaction reference-likeness scores | Prioritization, not truth |
| UniKP prediction | Yes, if substrate SMILES and enzyme sequence exist | kcat/Km/kcat_Km predictions | Predicted kinetic prioritization, not measured kinetics |
| External evidence tiering | Yes | exact/near/family/keyword evidence tiers | Literature/database support by tier |
| Engineering feasibility | Partly | target-specific feasibility matrix | Engineering risk, not reaction validation |
| Construct design | Partly | machine-readable hypothetical draft | Requires review; not a protocol or validated construct |

## Target-Specific Layers

These should remain outside the generic core until generalized:

- Target-specific candidate reactions and stoichiometry.
- Target-specific metabolite IDs and SMILES.
- P450-specific scoring rules, unless the target actually requires P450 chemistry.
- Construct/redox design recommendations.
- Literature conclusions specific to one molecule.

## Evidence Separation Rule

Never collapse these into one label:

- `model_feasible`
- `reaction_reference_like`
- `kinetically_promising`
- `external_exact_evidence`
- `engineering_feasible`
- `construct_priority`

Each answers a different question. A strong candidate should be strong across several layers, but weakness in one layer should remain visible.

Software release readiness means at least one shipped reference configuration can execute every stage it selects. Missing experimental validation, no exact evidence match, out-of-domain predictions, and hypothetical construct status remain scientific limitations in outputs; they do not by themselves mean the CLI is non-executable.
