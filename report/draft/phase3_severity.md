# Draft report section: Leaf masks and severity (Phase 3)

Draft written 2026-11-14 from `experiments/LOG.md`, `docs/phase3_plan.md`,
`report/tables/refinement_tuning.md`, `report/tables/pregold_round2.md` and
`report/tables/gold_evaluation.md`. TODO marks things still to be checked or
filled in.

## Methods

**Severity.** `severity = lesion pixels on the leaf / leaf pixels`, in percent.

**Gold standard.** Visual severity ratings by one rater (Adrija) on 54 test
images, locked before any method existed (tag `gold-v1`), with one click per
image on the main leaf. A blind recheck of 15 images gives the rater's
test-retest difference: **3.64 points**. This is used as the resolution limit:
it is shown beside every result, and two methods whose MAE differs by less are
reported as not distinguishable. 15 further rated images from the validation
split form the tuning set (12 after exclusions).

**Leaf mask.** SAM 2 (hiera tiny) with the stored click as one positive point;
of its 3 candidates, the highest-scoring one that covers at least 2% of the
image. The rule was chosen on the tuning images (4 combinations of model and
rule) and frozen before any gold image was processed. Each gold outline was
then checked (correct leaf, wrong leaf, not a leaf) without any severity shown;
37 of 53 images passed and form the evaluation set. The check was judged by an
AI assistant and verified by the rater.

**Methods compared**, all on the same leaf:
- A: PlantSeg's infected-region mask clipped to the leaf.
- B: the region predicted by SegFormer-B0 (Phase 2, retrained) clipped to the leaf.
- C: a colour refinement of A or B. Inside the region, keep pixels with the
  disease group's lesion colour in CIELAB: a* >= 10 for the rusts, a* >= 15 for
  septoria blotch and bacterial leaf streak, chroma <= 8 with L* >= 35 for
  powdery mildew. Yellow tissue that touches a kept pixel is added (chlorotic
  halo rule). One threshold per group, chosen from a grid of 5 values fixed in
  advance, by MAE on the 12 tuning images.

**Fallback and change rules, fixed in advance.** The tuned refinement (C1) is
used only if it beats an untuned green-removal rule (C0) by more than 3.64
points on tuning (it did: 12.1 points). A second tuning round before gold
(extended grids; halo optional for the necrotic group, after a stage-by-stage
diagnosis of the three worst tuning images) could change the method only if
leave-one-out MAE improved by more than 3.64 points. It improved by 2.2 and
1.9 points, so the method was kept.

**Evaluation.** The method was frozen and tagged, then gold was scored once.
Metrics: pooled MAE with a percentile-bootstrap 95% CI (1000 resamples), MAE by
disease and by rating band, and agreement of the severity level and decision
with those of the rating. **The level thresholds (5% and 20%) and the decision
mapping are placeholders, not validated against an agronomy source.**

## Results

Tuning (12 images, MAE in points): A 75.0, B 77.5, C0(B) 27.2, C1(B) 15.1
in-sample and 17.3 leave-one-out.

Gold (37 images; resolution limit 3.64 points beside every row):

| method | pooled MAE (95% CI) | mean signed error | same level | same decision | resolution limit |
|---|---|---:|---:|---:|---:|
| A | 65.65 (55.80-74.38) | +65.65 | 22% | 22% | 3.64 |
| B | 59.02 (48.99-67.39) | +58.85 | 19% | 19% | 3.64 |
| C(A) | 14.41 (10.05-19.27) | +1.28 | 24% | 24% | 3.64 |
| C(B) | 14.35 (9.97-19.23) | +1.22 | 24% | 24% | 3.64 |

The level columns are as written by the gold run, with the old level mapping. With the current
**placeholder** mapping (none = 0%, then 5% and 20%; decided 2026-11-14 after Phase 4), the same saved
severities give 22% (8 of 37) for all four methods (`report/tables/gold_levels_v2.md`). MAE is unchanged.

C(B) by rating band:

| band | n | MAE (95% CI) | resolution limit |
|---|---:|---|---:|
| low (< 10%) | 25 | 11.98 (6.48-18.98) | 3.64 |
| medium (10% to < 20%) | 6 | 11.51 (6.40-17.15) | 3.64 |
| high (>= 20%) | 6 | 27.05 (22.69-31.25) | 3.64 |

Without the one image whose disease label conflicts with a training copy
(36 images): C(B) 14.56 (10.03-19.97), same level 22% (old mapping; 19% with the current one).

- The raw regions are unusable as severity (59 to 66 points): they cover most
  of the leaf.
- The refinement removes most of that error, and the result no longer depends
  on which region it starts from (C(A) and C(B) are not distinguishable).
- The refined estimate is still about four times the rating noise, and its
  level agrees with the rating's level on 22% of images (current placeholder levels; 24% with the old
  mapping).

## Limitations

See `report/limitations.md` (sections on the gold ratings, the leaf check, and
the gold evaluation). In short: one rater; AI-judged leaf check; 37 images;
thresholds tuned on 12 images; the colour rule is the failing stage; the
rating and the method may not count the same tissue; placeholder thresholds.

TODO: agronomy source for the severity levels and the halo rule.
TODO: decide whether Phase 5 or 6 should replace the colour rule or only
report its instability.
