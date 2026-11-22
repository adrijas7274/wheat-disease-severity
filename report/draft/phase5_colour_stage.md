# Draft report section: Making the colour stage robust (Phase 5)

Draft written 2026-11-16 from `experiments/LOG.md` and
`report/tables/phase5_colour_stage.md`. TODO marks things still to be checked or filled in.

**Status (2026-11-18): the final pipeline uses NO colour preprocessing.** Sections v1 below are
the pre-registered Phase 5 result, kept as history; its stability gain (flip rate 0.32 -> 0.20)
is **not** a result of the final pipeline. The post-hoc v2 (last section) added per-disease
guards and selected no preprocessing for every disease group.

## Methods

**Why the colour stage.** Phase 4 showed that the severity estimate moves most under
corruptions that change colour or brightness, and that the two region models flip equally
often. The fragile part is the colour rule, so Phase 5 was redirected (2026-11-14) from
corruption-augmented training alone to preprocessing in front of the colour rule.

**Variants.** Twelve combinations of four steps, applied to the image for the colour rule
only (the region model and SAM 2 see the photo as it is): gray-world and shades-of-gray
(p = 6) colour constancy, an exposure gain that sets the mean luminance to 0.18 in linear
light, and a light Gaussian denoise (sigma 1.5 px at a 1024 px long side). For each variant
the colour thresholds were re-tuned on the 12 tuning images with the Phase 3 grid and rules.

**Selection rule**, written and committed before any result: a variant is admissible if its
tuning leave-one-out MAE is at most 3.64 points (the rater's test-retest MAE) worse than no
preprocessing; among admissible variants the lowest mean severity shift on the test split
wins; it replaces the baseline only if its shift is lower and its flip rate is not higher.
Gold was not used.

**Evaluation.** The Phase 4 benchmark (ten corruptions, five levels, 121 test images), from a
cache of leaf and region masks per condition. The mean severity shift over the 50 cells is
the primary, threshold-free metric. Flip rates use the **placeholder** levels and decision
mapping; corruption levels are placeholders. The 78 validation images are reported as a
check, because the selection itself uses the test split.

**Baseline.** One SegFormer-B0 trained with corruption augmentation (probability 0.5, random
type and level), used as the region model with the same leaf and colour rule.

## Results (v1, pre-registered; history, not the final pipeline)

Selected: denoise, then shades-of-gray, then exposure (thresholds rust 5, necrotic 15,
mildew 8). All 12 variants were admissible.

| colour stage | test shift, points | test flip rate | val shift | val flip rate | tuning leave-one-out MAE |
|---|---:|---:|---:|---:|---:|
| none (Phase 3 method; final pipeline after v2) | 5.71 | 0.32 | 6.22 | 0.33 | 17.30 |
| v1 selected (history) | 4.27 | 0.20 | 3.58 | 0.21 | 19.23 |

**The selected stage is a trade-off, not a uniform gain.** It is better on colour cast,
under-exposure and sensor noise, and worse on JPEG, low resolution and the combined chain
(test, level 5, no preprocessing -> selected):

| corruption | severity shift, points | flip rate | direction |
|---|---|---|---|
| colour cast | 16.8 -> 4.9 | 0.67 -> 0.19 | better |
| under-exposure | 11.7 -> 3.1 | 0.55 -> 0.12 | better |
| sensor noise | 14.2 -> 9.0 | 0.58 -> 0.52 | better |
| JPEG | 6.8 -> 6.9 | 0.26 -> 0.37 | worse |
| low resolution | 4.0 -> 5.7 | 0.30 -> 0.24 | worse on shift, better on flip rate |
| combined chain | 6.9 -> 8.8 | 0.36 -> 0.45 | worse |

Over-exposure (12.9 -> 12.8) and the three blurs (Gaussian 7.5 -> 7.6) do not change in
shift. The combined chain is worse from level 3 upwards (shift 3.7 -> 4.9 at level 3).

Region model (test): the corruption-augmented SegFormer-B0 has a higher mean mIoU over the 50
cells (0.640 against 0.614) and the same severity shift (5.69 against 5.71 without
preprocessing, 4.29 against 4.27 with it).

Combined-chain ablation (shift at level 5, no preprocessing): noise 14.2, noise then JPEG
6.0, low resolution then noise 15.6, full chain 6.9.

Figures: `report/figures/phase5/variants.png`, `severity_shift_vs_level.png`,
`flip_rate_heatmap.png`, `*_ablation.png`.

## v2 (post hoc): per-group colour stage with guards

**Why.** Phase 7 showed that the v1 stage suppresses the necrotic rule (below). Adrija decided
(2026-11-18) on one post-hoc round, labelled as such, with v1 kept unchanged.

**Rules** (`configs/experiments/phase5_v2.yaml`, tagged `phase5-v2-prereg` before any v2 result).
One variant per refinement group (rust, necrotic, mildew), from the same 12 including none,
chosen on tuning and validation data only. Guards against no preprocessing: G1 per-group tuning
leave-one-out MAE at most 3.64 points worse; G2 per disease, clean validation zero rate not
higher; G3 on 250 healthy wheat field photos (Bangladesh, Mendeley 5gc7hwydwg, originals only;
PlantSeg has no healthy images), median false severity and share above 5% not higher. Among
passing variants: lowest validation shift, then flip rate; it replaces none only if the shift is
lower and the flip rate not higher. Test was evaluated once, afterwards.

**Result: in every group, only no preprocessing passes all three guards.** Every more stable
variant raises a disease's zero rate (G2), raises false alarms on healthy leaves (G3; the
gray-world variants put 44-47% of healthy leaves above 5% under the mildew rule), or loses tuning
accuracy (G1). So v2 = the Phase 3 colour stage.

Test (single evaluation), v1 -> v2:

| disease | n | clean zero rate | mean shift, points | flip rate |
|---|---:|---|---|---|
| stripe rust | 43 | 16% -> 26% | 4.15 -> 5.23 | 0.20 -> 0.30 |
| leaf rust | 9 | 22% -> 11% | 4.27 -> 6.27 | 0.16 -> 0.25 |
| septoria blotch | 24 | 50% -> 29% | 4.98 -> 9.62 | 0.27 -> 0.36 |
| bacterial leaf streak | 17 | 65% -> 47% | 2.13 -> 3.79 | 0.15 -> 0.30 |
| powdery mildew | 28 | 7% -> 21% | 5.14 -> 4.09 | 0.20 -> 0.34 |
| pooled | 121 | 28% -> 27% | 4.27 -> 5.71 | 0.20 -> 0.32 |

Healthy photos (Bangladesh, n = 250), share above 5%, v1 -> v2: rust rule 10% -> 8%, necrotic
2% -> 6%, mildew 15% -> 4%; median 0% throughout. Table: `report/tables/phase5_v2.md`.

**Finding: within the guards, colour preprocessing trades detection for stability, and no
variant improved robustness.** The v1 gain came largely from answering 0% more often on necrotic
diseases and from more false alarms on healthy leaves under the mildew rule.

## Limitations

- The selection uses the test split, so the selected variant's test numbers are optimistic.
  The validation split agrees on the first place.
- The selected variant has the worst tuning leave-one-out MAE of the twelve (1.93 points
  above the baseline, inside the guard). Its error against the gold ratings is not known:
  gold was scored once, with the Phase 3 method.
- **Trade-off.** The selected stage is better on colour cast, under-exposure and sensor noise
  and worse on JPEG, low resolution and the combined chain. The mean over the 50 cells, which
  the selection rule uses, hides this. The rule was fixed before the results and was followed.
- **Found in Phase 7: the selected stage suppresses the necrotic rule.** On clean PlantSeg photos
  the share of septoria estimates at exactly 0% rises from 29% to 50% (test) and 19% to 62% (val),
  and of bacterial leaf streak from 47% to 65% (test). On new-source septoria photos it detects 6%,
  against 84% without preprocessing. The overall zero share (27% against 28%) that Phase 5 checked
  hid this, because powdery mildew moved the other way. Part of the stability gain on necrotic
  diseases is therefore from answering 0%. The selection rule had no per-disease guard.
- **Corruption levels are uncalibrated placeholders.** The combined chain (low resolution,
  then noise, then JPEG, same level for each step) is a hand-set composition, not a measured
  model of a cheap phone. So neither the loss on the combined chain nor the mean over
  corruptions says how the stage behaves on real low-end phone photos; that needs real
  photos (Phase 7, `data/own_photos/`).
- Stability is measured against the same method on the clean photo, not against a rating.
- Twelve tuning images; one seed per model; placeholder corruption levels, severity
  thresholds and decision mapping.
- **v2 is post hoc and its guards are strict.** G2 compares zero rates on small validation
  groups (leaf rust 5, bacterial leaf streak 11, septoria 16 images), so one image can decide it,
  and ties favour no preprocessing. A looser guard might keep a variant; that was not tried, to
  avoid a third post-hoc round.
- The final pipeline therefore has no protection against colour cast and exposure beyond the
  Phase 6 gate (colour cast at level 5: shift 16.8 points, flip rate 0.67).
- TODO: decide whether the report's headline uses the mean over cells or per-corruption numbers.
