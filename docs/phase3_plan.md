# Phase 3 method plan

Written 2026-11-11, **before any Phase 3 method code exists**. Decisions marked
"(Adrija)" were made by Adrija on 2026-11-11. The evaluation rules themselves
are in `docs/annotation_guidelines.md` (*Evaluation plan*); this file is the
method and the order of work.

Status when written: gold ratings locked (tag `gold-v1`), blind recheck done,
no leaf masks, no refinement, no tuning, nothing scored against gold.

## Fixed numbers this plan relies on

- **Resolution limit: 3.64 points** (Adrija). This is the rater's test-retest
  mean absolute difference on the 14 recheck images that stay in evaluation
  (bootstrap 95% CI 2.04 to 5.46, Lin's CCC -0.07). On all 15 recheck images it
  is 3.40.
- **Gold evaluated set:** at most 53 images (54 minus the one in
  `annotation.gold_exclude`), before the wrong-leaf check.
- **Tuning set:** 12 images (15 minus the three in `annotation.tuning_exclude`):
  stripe rust 2, leaf rust 2, powdery mildew 3, septoria blotch 3, bacterial
  leaf streak 2. It was 14 when this plan was first written; two spike photos
  were excluded later on 2026-11-11 (Adrija), before any tuning.
- Severity thresholds and the decision mapping in `configs/config.yaml` are
  **PLACEHOLDERS**, not validated against an agronomy source.

## 1. Leaf mask from the click

- **Rule:** SAM 2 (the config's `sam2` model, hiera tiny), the stored click as
  one positive point, highest-scoring of 3 candidate masks. This is the rule
  already fixed in the guidelines.
- **Known failure:** SAM sometimes returns a part of the leaf, such as a
  pustule cluster, instead of the whole leaf.
- **One alternative, tested on the tuning images only:** the largest of the 3
  candidate masks that contains the click. Result (2026-11-11): neither rule
  is usable, see `report/tables/leaf_mask_tuning.md`.
- **Revised comparison (Adrija, 2026-11-11):** four combinations on the 12
  tuning images: {SAM 2 tiny, SAM 2 base+} x {`best_score`, `min_area`}.
  `min_area` keeps the highest-scoring candidate that covers at least 2% of the
  image, or the largest candidate if none does.
- **Decision:** Adrija marks every distinct outline "whole main leaf: yes / no"
  in a review screen, shuffled and with model and rule names hidden
  (`src/severity/leaf_rule_review.py`). The combination with the most "yes"
  wins. Ties go to tiny over base+, then `best_score` over `min_area`. The
  winner is frozen in the config before any gold image is processed.
- **Outcome (2026-11-11):** the outlines were judged by Claude (AI) at Adrija's
  request and all 29 verdicts were checked and accepted by Adrija. "Yes" out
  of 12: tiny + `min_area` 10, the other three 9 each. **Frozen: SAM 2 tiny +
  `min_area` (2%).** The margin is one image.
- **Wrong-leaf check on gold:** Adrija marks each gold SAM outline correct
  leaf, wrong leaf or not a leaf, with no severities and no lesion masks shown.
  Wrong-leaf and not-a-leaf images are excluded (rule fixed 2026-11-02; the
  not-a-leaf option added 2026-11-11). Needs a small review tool.
- **Who judged (changed 2026-11-14, Adrija's decision):** the 53 outlines were
  judged by Claude (AI) from the overlays only (photo, gold click, outline),
  before any severity was computed on gold. Adrija checks the contact sheet
  (`report/figures/leaf_masks/leaf_check_sheet.png`) and the notes
  (`report/tables/leaf_check_notes.csv`) and can override. The leaf rule being
  checked was also designed by Claude. This is weaker than a blind human
  check. **Checked by Adrija and locked on 2026-11-14** (tag `leaf-check-v1`).
  She added the partial-leaf rule (an outline is correct only if it covers
  about three-quarters or more of the clicked leaf's visible area), which
  turned 4 "correct" verdicts into "wrong", and accepted the rest.
- **Gold evaluation set after the check: 37 images** (stripe rust 8, leaf rust
  5, powdery mildew 8, septoria blotch 9, bacterial leaf streak 7). Of the 53
  checked: 10 wrong leaf, 3 not a leaf, 2 collages and 1 duplicate photo
  (the last three through `annotation.gold_exclude`).
  `leaf_check_tool.evaluated_gold_rows` returns the 37.

## 2. Methods compared, all on the same SAM leaf

Each gives `severity = lesion pixels on leaf / leaf pixels`.

- **A:** PlantSeg's infected-region mask clipped to the leaf.
- **B:** the Phase 2 model's predicted infected region clipped to the leaf.
  The model is chosen from `report/tables/baselines.md` and fixed before
  scoring.
- **C0:** A or B with healthy-green pixels removed, using the existing untuned
  green range from `src/severity/mask_coarseness_check.py`. No tuned parameters.
- **C1:** per-disease refinement (section 3).
- C is applied to both inputs: on A it isolates the refinement, on B it is what
  the app would run.

## 3. Lesion refinement per disease (C1)

Keep only pixels inside the infected region and the leaf that match the
disease's lesion colour, in Lab colour space. Refinement can only shrink a
region: lesions the region mask missed stay missed.

| disease group | pixels kept |
|---|---|
| stripe rust, leaf rust | orange to orange-brown |
| septoria blotch, bacterial leaf streak | brown necrotic |
| powdery mildew | white or grey, low saturation |

Chlorotic halos follow the placeholder rule in the guidelines.

## 4. Tuning on the tuning images (12 after exclusions; 14 when this was written)

- **Budget:** one threshold per disease group, chosen from a grid of about 5
  values written into the experiment config before any result is looked at.
  With 2 to 3 images per disease and 3.64 points of rating noise, more
  parameters would fit noise.
- **Objective:** severity MAE against the tuning ratings. Leave-one-out error
  is reported to show how stable the choice is.
- **Fallback rule (Adrija):** C1 is used only if it beats C0 on tuning MAE by
  more than 3.64 points. Otherwise C0 is the method.

- **Details settled on 2026-11-14, before any refinement result existed**
  (Claude, routine decisions under the fast working mode, logged in
  `experiments/LOG.md`): the grids in
  `configs/experiments/phase3_refinement.yaml`; rust and necrotic groups keep
  pixels with Lab a* at or above the threshold, mildew keeps pixels with Lab
  chroma at or below it and L* of at least 35; thresholds are tuned on input B
  and applied to both inputs; yellow tissue (HSV hue 15 to 24) in the region
  is added when it touches a kept lesion pixel.
- **Outcome (2026-11-14, `report/tables/refinement_tuning.md`):** thresholds
  rust 10, necrotic 15, mildew 8. Tuning MAE on B: C0 27.24, C1 15.11
  (leave-one-out 17.30). C1 beats C0 by 12.13 points, more than 3.64, so
  **C1 is the method**. Frozen in the config (`severity_method`), tag
  `phase3-method-v1`. Two of the three thresholds are at the edge of their
  grid; the grid was not extended, because that would be a second round of
  tuning.

- **Pre-gold round 2 (Adrija, 2026-11-14), tuning images only:** one time-boxed
  round before gold, with a change rule fixed in advance: the method changes
  only if leave-one-out MAE improves by more than 3.64 points. The three worst
  tuning images all failed in the colour stage (two through the halo rule).
  Candidates (`configs/experiments/phase3_round2.yaml`, committed before their
  results): extended necrotic and mildew grids (E), and E with the halo
  optional for the necrotic group (F). Leave-one-out MAE: v1 17.30, E 15.09,
  F 15.42. Gains of 2.21 and 1.88 points do not pass the rule, so
  **`phase3-method-v1` is kept** (`report/tables/pregold_round2.md`).
- **black_chaff (25) (Adrija, 2026-11-14):** this gold image has a conflicting
  disease label in a training copy. It keeps its PlantSeg label, and the gold
  report gives every headline result with and without it.

## 5. Evaluation against gold, once

**Done on 2026-11-14** at tag `phase3-pregold-round2` (method `phase3-method-v1`):
`report/tables/gold_evaluation.md`. C(B) pooled MAE 14.35 points (95% CI 9.97
to 19.23) on 37 images. The script refuses a second run.

- **Freeze first:** code, config and commit are tagged before any gold image is
  scored. No re-tuning afterwards; more tuning would be a new round on the
  tuning set.
- **Metrics:** as in the evaluation plan (pooled MAE with bootstrap CI, per
  disease, by rating band, level and decision agreement, exclusion counts).
- **Resolution limit:** 3.64 points shown beside every result. Methods whose
  MAE differs by less are reported as not distinguishable at the gold
  standard's resolution.
- **Role:** severity accuracy against gold is a secondary result. Phase 4
  consistency is the primary one.

## 6. Second rater

**Decided: no second rater (Adrija, 2026-11-14).** All gold ratings and clicks
come from one rater, so there is no inter-rater agreement figure and no check
on that rater's bias. The only repeatability evidence is the blind recheck by
the same rater. This single-rater limitation is reported in
`report/limitations.md` beside the results.

## 7. Leaf masks where there is no stored click (Adrija)

Written down now, before Phase 4 exists.

- **App:** the farmer taps the leaf. Phase 8 gains a task: test a phone-sized
  promptable segmentation model and report its size and latency.
- **Phase 4, automatic click rule (confirmed by Adrija, 2026-11-11):**
  - The infected-region prediction comes from **SegFormer-B0** on the **clean**
    image. Every benchmarked model uses this same click.
  - The click is the **point deepest inside the largest predicted infected
    component**: the pixel with the highest distance-transform value, so it is
    always on predicted tissue and away from the component's edge.
  - If nothing is predicted, the click is the image centre.
  - The **same click is reused for every corrupted version** of that image.
  - **SAM is re-run on every corrupted version** with that click, so a change in
    the leaf mask under corruption counts as part of the severity shift.
- **Phase 4 cross-check:** Phase 4 is also run on the gold images with Adrija's
  real clicks.

Implementation details, Claude's and not separately confirmed: "largest" is by
pixel count with 8-connectivity at the model's output resolution; the click is
mapped back to original-image pixels; if several pixels share the highest
distance value, the first in row-major order is used.

## 8. Code

- New modules in `src/severity/`: leaf mask, refinement, wrong-leaf check tool,
  evaluation script with `--debug`.
- One experiment YAML; outputs in `experiments/<timestamp>_<name>/`.
- Tests for each new module.

## Order of work, with a stop after each step

1. Leaf masks on tuning, and the prompting rule decision.
2. Wrong-leaf check on gold.
3. Refinement and tuning.
4. Freeze, then the single gold evaluation and report.
