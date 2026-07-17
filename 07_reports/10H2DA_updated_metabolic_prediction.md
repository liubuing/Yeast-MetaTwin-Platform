# 10H2DA Updated Metabolic Prediction

Target: 10-Hydroxy-trans-2-decenoic acid, 10H2DA, C10H18O3.

Date: 2026-07-16.

## Conclusion

10H2DA is still not a native model metabolite in yeast-GEM or Yeast-MetaTwin. The updated deployment tables strengthen the evidence for the upstream C10 fatty-acid and trans-2-enoyl-CoA precursor route, but the final target-forming reactions remain candidate extensions.

Most supported route:

```text
decanoate
  -> decanoyl-CoA
  -> trans-dec-2-enoyl-CoA
  -> trans-2-decenoic acid or 10-hydroxy-trans-2-decenoyl-CoA candidate intermediate
  -> 10-Hydroxy-trans-2-decenoic acid
```

Current confidence: medium-high for reaching `trans-dec-2-enoyl-CoA`; medium for model feasibility of 10H2DA after adding balanced candidate terminal reactions; still medium/low for biological enzyme specificity because terminal omega-hydroxylation and exact enoyl-CoA thioesterase release are not model-native.

## Model Coverage

| Query | Result |
|---|---|
| 10H2DA / 10-Hydroxy-trans-2-decenoic acid | No exact model metabolite match |
| Formula C10H18O3 | No exact model metabolite match |
| decanoate | Present, mapped, externally cross-referenced |
| decanoyl-CoA | Present, mapped, externally cross-referenced |
| trans-dec-2-enoyl-CoA | Present, mapped, externally cross-referenced |
| (R)-3-hydroxydecanoyl-CoA | Present, mapped, externally cross-referenced |

## Core Reaction Evidence

| Step | Model reaction | Evidence tier | Enzyme / ORF | Comment |
|---|---|---|---|---|
| decanoate -> decanoyl-CoA | `r_0399` fatty-acid--CoA ligase (decanoate) | `external_crossref` | FAA2 / YER015W | Strong model-native entry into C10 acyl-CoA metabolism. |
| decanoyl-CoA -> trans-dec-2-enoyl-CoA | `r_0120` acyl-CoA oxidase (decanoyl-CoA) | `external_crossref` | POX1 / YGL205W | Strong model-native formation of the trans-2-enoyl-CoA backbone. |
| decanoyl-CoA -> decanoate | `r_0844` peroxisomal acyl-CoA thioesterase | `external_crossref` | TES1 / YJR019C | Supports C10 acyl-CoA hydrolysis, but not the exact trans-2-enoyl-CoA hydrolysis needed for trans-2-decenoic acid. |
| trans-dec-2-enoyl-CoA -> 3-hydroxydecanoyl-CoA | `r_2248` 2-enoyl-CoA hydratase | `external_crossref` | FOX2 / YKR009C | Shows the model can further metabolize this C10 enoyl-CoA node. It is not the target-forming step. |
| underground contribution to trans-dec-2-enoyl-CoA | `rxn1937` | `prediction_provenance` | Multiple acyl-CoA ligase ORFs | RXNdb direct provenance, template `MNXR176705`, EC `2.7.8.29`, similarity `0.9038461538|1.0`; useful candidate evidence, not curated validation. |

## Homology Split Context

The updated MMseqs2 split does not change the biochemical route, but it improves confidence in the evidence audit. The key model-supported enzymes map to homology split clusters without cluster crossing across train/dev/test in the deployment split files.

Important detail: several reactions using the same enzyme family are assigned by homology cluster rather than raw reaction equation. This reduces sequence-family leakage for future enzyme-model evaluation, but it does not prove 10H2DA production experimentally.

## Updated Pathway Ranking

| Rank | Route | Current assessment |
|---:|---|---|
| 1 | decanoate -> decanoyl-CoA -> trans-dec-2-enoyl-CoA -> candidate release/hydroxylation -> 10H2DA | Best supported. Upstream C10 trans-2 precursor is model-native; final target steps are extensions. |
| 2 | decanoate -> 10-hydroxydecanoate -> 10-hydroxydecanoyl-CoA -> 10-hydroxy-trans-2-decenoyl-CoA -> 10H2DA | Plausible but less model-supported; hydroxy-C10 intermediates are absent. |
| 3 | longer-chain omega-hydroxy fatty acid beta-oxidation shortening to C10 hydroxy-trans-2 product | Exploratory; requires more chemistry validation and metabolite/reaction additions. |

## Missing Reactions To Close The Path

Minimal candidate additions:

```text
trans-dec-2-enoyl-CoA + H2O -> trans-2-decenoic acid + CoA
```

```text
trans-2-decenoic acid + NADPH + O2 -> 10-Hydroxy-trans-2-decenoic acid + NADP+ + H2O
```

Alternative CoA-bound route:

```text
trans-dec-2-enoyl-CoA + NADPH + O2 -> 10-hydroxy-trans-2-decenoyl-CoA + NADP+ + H2O
```

```text
10-hydroxy-trans-2-decenoyl-CoA + H2O -> 10-Hydroxy-trans-2-decenoic acid + CoA
```

Candidate enzyme classes:

- enoyl-CoA thioesterase / acyl-CoA thioesterase for product release.
- CYP52-like fatty acid omega-hydroxylase or other P450/monooxygenase for terminal C10 hydroxylation.

## Candidate Extension FBA

The candidate extension was tested in memory without modifying the source Yeast-MetaTwin YAML model.

| Scenario | Objective | Biomass floor | Max flux | Interpretation |
|---|---|---:|---:|---|
| target demand only | `DM_s_1507` | none | 0.140091 | Native model can produce the CoA-bound C10 precursor. |
| target demand only | `DM_CAND_10H2DA_P` | none | 0 | 10H2DA remains absent without terminal candidate chemistry. |
| free-acid terminal route | `DM_CAND_10H2DA_P` | none | 0.302724 | Feasible after thioesterase plus free-acid hydroxylase additions. |
| free-acid terminal route | `DM_CAND_10H2DA_P` | 10% native biomass | 0.274011 | Feasible while retaining growth. |
| CoA-bound terminal route | `DM_CAND_10H2DA_P` | none | 0.302724 | Feasible after CoA-bound hydroxylase plus thioesterase additions. |
| CoA-bound terminal route | `DM_CAND_10H2DA_P` | 10% native biomass | 0.274011 | Feasible while retaining growth. |

All four terminal candidate reactions used in the test are formula-balanced and charge-balanced in the Phase 2 training-readiness audit.

Report: `07_reports/10H2DA_candidate_extension_fba.md`.

## Training Readiness Context

The updated training-readiness audit adds reaction balance, feature coverage, conservative negative-sample design, and validation action flags.

| Item | Value |
|---|---:|
| Model reactions checked for balance | 7512 |
| Formula-balanced model reactions | 4792 |
| Charge-balanced model reactions | 5059 |
| 10H2DA candidate terminal reactions checked | 4 |
| 10H2DA candidate terminal reactions formula-balanced | 4 |
| 10H2DA candidate terminal reactions charge-balanced | 4 |
| Candidate unlabeled hard negatives | 1886 |
| Validation matrix rows | 5344 |

The negative pool should not be treated as true negative biochemistry. It is an unlabeled hard-negative pool for conservative model training or positive-unlabeled learning.

## Practical Next Step

To move from feasibility to stronger prediction, prioritize enzyme/database validation for the terminal thioesterase and omega-hydroxylase candidates, then promote only externally supported terminal reactions into the curated label set.
