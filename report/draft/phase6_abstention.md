# Draft report section: Quality gate, uncertainty and abstention (Phase 6)

Draft written 2026-11-17 from `experiments/LOG.md` and `report/tables/abstention.md`. TODO
marks things still to be checked or filled in.

## Methods

**Method under evaluation.** SegFormer-B0 infected region, SAM 2 leaf from the automatic click,
and the colour stage selected in Phase 5 (denoise, shades-of-gray, exposure; thresholds rust 5,
necrotic 15, mildew 8). Copied into `configs/experiments/phase6_abstention.yaml` and committed
before any Phase 6 result.

**Error.** An estimate's error is its distance from the same method's estimate on the clean
photo: severity shift in points, and decision flip with the **placeholder** levels and mapping.
An estimate is "unreliable" if its shift exceeds 3.64 points (the rater's test-retest MAE).
This measures stability, not correctness: test images have no ratings, and the method is about
14 points from gold on clean photos.

**Quality gate** (image only, runs before any model): sharpness (Laplacian variance), noise
(Immerkaer's estimate), mean brightness, clipped highlights and shadows, and a minimum side of
224 px. A photo fails ("please retake the photo") if a feature falls outside the 2.5th
percentile on its bad side of the clean validation photos, so about 2.5% of clean photos are
sent back per check and side (the rates add up over the checks; see Results). A framing check (leaf share of the image) is reported
separately, because the photo checks cannot see framing.

**Uncertainty scores**, all cheap enough for a phone:
- softmax entropy of the region model inside its predicted region;
- mirror test-time augmentation: spread of the severity over left-right and up-down flips;
- photometric test-time augmentation: spread of the severity when the photo is made slightly
  brighter, darker, warmer and cooler before the colour rule (no extra network call);
- threshold margin: distance of the estimate from the nearest placeholder level boundary;
- two tiny logistic-regression classifiers predicting "unreliable": one on the gate features,
  one on gate features plus the scores above.

**Policy.** Gate fails -> "retake the photo"; otherwise policy score above a threshold ->
"consult an expert"; otherwise answer. The policy score (lowest shift AURC), the classifiers,
the gate ranges and the thresholds for 80% and 90% target coverage are all fitted on the
**validation** split (78 images). The test split (121 images, ten corruptions x five levels)
is only evaluated. Gold is not used.

**Evaluation.** Risk-coverage curves for severity shift and flip rate; AURC; risk at 80% and
90% coverage with cluster-bootstrap 95% intervals (images resampled); the full policy's
retake / consult / answer shares on corrupted and clean test photos; the gate's retake rate and
its catch rate among unreliable estimates per corruption and level, to see whether the gate
covers Phase 5's weak spots (JPEG, low resolution, combined chain); and the gate on the
`wide` and `skip` images, which the segmentation model never trains on.

## Results: v1 (pre-registered, tag `phase6-v1`)

The rules above were fixed before any Phase 6 result; these are the v1 numbers, unchanged.

Corrupted test photos: 121 images x ten corruptions x five levels = 6050 estimates. Without
abstention the mean severity shift is 4.27 points and the flip rate 0.20 (placeholder mapping).

**Uncertainty scores** (test; AUROC for "shift > 3.64"; risk at 80% coverage, 95% CI for shift):

| score | AUROC | shift AURC | shift at 80% | flip rate at 80% |
|---|---:|---:|---|---:|
| softmax entropy | 0.54 | 4.00 | 4.53 (3.35-5.75) | 0.19 |
| mirror TTA spread | 0.70 | 2.54 | 3.35 (2.30-4.52) | 0.18 |
| photometric TTA spread | 0.74 | 2.34 | 3.51 (2.41-4.64) | 0.20 |
| threshold margin | 0.27 | 6.89 | 4.90 (3.83-6.17) | 0.21 |
| classifier, gate features | 0.63 | 3.28 | 3.56 (2.55-4.70) | 0.18 |
| classifier, gate features + scores (policy, chosen on val) | 0.76 | 2.45 | 2.86 (1.91-3.88) | 0.20 |
| oracle (true shift) | 1.00 | 0.46 | 0.77 (0.56-1.04) | 0.13 |

**Error reduction with the policy score:** at 80% coverage the shift falls from 4.27 to 2.86
points (-33%) and the flip rate stays at 0.20 (-2%); at 90%, 3.34 (-22%) and 0.20 (-4%).
Abstention makes the answered estimates more stable in points but barely changes how often
the decision flips.

**Why abstention reduces shift but not flips.** The estimates sit close to the placeholder
thresholds: half of the clean test estimates are below 5% (28% are exactly 0, 22% between 0 and
5%; median 4.9%), and 16% are within 3 points of 5%. A flip then needs only a small shift across
a boundary, and every score, built to predict large shifts, ranks such an estimate as reliable.
Even ordering the estimates by their true shift leaves a flip rate of 0.13 at 80% coverage. The
flips cross the 0% boundary (none = exactly 0) as often as the 5% one, so the clustering that
matters is around both the lower boundaries, not only 5%.

**Zero estimates on diseased leaves.** Every PlantSeg test photo shows a diseased leaf, yet 28%
of the clean test estimates are exactly 0% (decision "no action"). These are possibly missed
mild disease: the colour rule found no lesion-coloured pixel inside the predicted region on the
leaf. Test photos have no severity ratings, so how many of them are truly near 0% is unknown.

Share of answered corrupted estimates
on the other side of a single threshold than the clean estimate (v1 policy score):

| coverage | full mapping | 0% | 3% | 5% | 10% | 20% |
|---:|---:|---:|---:|---:|---:|---:|
| 80% | 0.20 | 0.10 | 0.09 | 0.10 | 0.06 | 0.04 |
| 90% | 0.20 | 0.10 | 0.09 | 0.10 | 0.07 | 0.04 |
| 100% | 0.20 | 0.10 | 0.09 | 0.10 | 0.08 | 0.06 |

At the higher thresholds (10%, 20%) abstention removes some flips; at 0%, 3% and 5% it removes
none.

**Quality gate.** It sends back 55% of corrupted test photos (mean shift 5.00 points when it
fails, 3.40 when it passes) and 19% of clean test photos (15% on validation). Catch rate among
unreliable estimates (shift > 3.64), all levels pooled:

| corruption | unreliable | gate catch rate | catch rate at level 5 |
|---|---:|---:|---:|
| over-exposure | 40% | 90% | 98% |
| Gaussian blur | 21% | 87% | 100% |
| sensor noise | 40% | 85% | 99% |
| under-exposure | 8% | 81% | 100% |
| defocus blur | 19% | 79% | 100% |
| low resolution | 14% | 62% | 86% |
| motion blur | 18% | 50% | 72% |
| colour cast | 16% | 34% | 36% |
| JPEG | 19% | 21% | 12% |
| combined chain | 32% | 14% | 8% |

The gate catches exposure and noise, where Phase 5's colour stage already helped, and misses
the corruptions where the colour stage got worse: JPEG and the combined chain are sent back at
about the clean-photo rate, and low resolution mainly at high levels. Colour cast, which
Phase 5 fixed, is also mostly missed by the gate.

**Full policy.** The gate refuses about half of the corrupted validation photos, so the 80% and
90% target coverages cannot be reached and the uncertainty step never refers a photo to an
expert. In practice the policy is the gate alone: on corrupted test photos it answers 45%
(shift 3.23 answered against 5.13 refused; flip rate 0.16 against 0.24), and on clean test
photos it answers 81%.

**Gate test set.** Of the 23 `skip` images, 61% fail a photo or the framing check (30% a photo
check, 43% framing). The planned non-disputed `wide` set is empty; the 21 disputed `wide`
images fail 29% of the time.

Figures: `report/figures/phase6/risk_coverage.png`, `report/figures/phase6/gate_retake_rate.png`.

## Results: v2 (POST HOC, tag `phase6-v2-prereg` for the rules)

v2 was decided after the v1 test results were seen and is labelled post hoc. Its rules and code
were committed and tagged before its single test evaluation; everything was fitted on validation.
Changes: one overall 5% false-retake target on clean validation photos split evenly over the check
sides, with the minimum side fitted instead of the fixed 224 px; a JPEG blockiness check; coverage
measured among gate-passed photos; classifiers tuned and the policy score chosen by grouped 5-fold
cross-validation inside validation. Full table: `report/tables/abstention_v2.md`.

**Gate.** Clean test photos sent back: **7%** (v1 19%); corrupted test photos 44% (v1 55%). On 78
validation photos the 5% budget could not be split finely: any tail above zero sends back the most
extreme photo on each of the eight check sides (9%). The fitted gate is therefore the min-max range
of the clean validation photos (minimum side 169 px; 4 of 78 validation and 6 of 121 test photos
are below the old 224 px). Its test false-retake rate (7%) is above the 5% target.

**Abstention among gate-passed photos** (3400 of 6050 corrupted estimates; policy score: tiny
classifier on gate features and scores): shift 3.31 -> 1.97 points at 80% coverage (-41%, 95% CI
1.21-2.84) and 2.30 at 90% (-31%); flip rate 0.17 -> 0.17 and 0.16.

**Full policy** at the 80% target: corrupted test photos 44% retake, 12% consult an expert, 44%
answered (shift of answered 1.91 points against 4.27 with no policy; flip rate 0.17 against 0.20).
Clean test photos: 7% retake, 20% consult, 73% answered. At the 90% target, consult falls to 6%
(corrupted) and 9% (clean).

**Catch rates on Phase 5's weak spots** (share of unreliable estimates refused):

| corruption | gate v1 | gate v2 | gate v2, level 5 | full policy v2 (80%) |
|---|---:|---:|---:|---:|
| JPEG | 21% | 43% | 84% | 76% |
| combined chain | 14% | 31% | 81% | 75% |
| low resolution | 62% | 46% | 76% | 60% |
| colour cast | 34% | 15% | 17% | 78% |
| over-exposure | 90% | 60% | 91% | 88% |
| sensor noise | 85% | 83% | 97% | 94% |

The blockiness check catches heavy JPEG and the combined chain at level 5 but not at levels 1-4
(combined chain 4-11%). The looser gate catches fewer exposure and colour-cast problems; the
uncertainty step catches most of them instead.

**Flips by threshold** (v2 policy, gate-passed, 80% coverage): 0%: 0.09, 3%: 0.07, 5%: 0.08,
10%: 0.04, 20%: 0.03. Same pattern as v1.

Figures: `report/figures/phase6_v2/risk_coverage.png`, `report/figures/phase6_v2/gate_retake_rate.png`.

## Results: final pipeline (Phase 6 v2 rules re-fitted on the Phase 5 v2 colour stage)

The v1 and v2 sections above use the Phase 5 v1 colour stage, which is no longer the final
pipeline (Phase 5 v2 selected no preprocessing for every disease group). Adrija decided
(2026-11-18) to re-run the frozen Phase 6 v2 rules on the Phase 5 v2 stage: every val and test
condition re-scored, gate, policy score and thresholds re-fitted on validation, test evaluated
once. No rule was changed. Table: `report/tables/abstention_final.md`.

**Gate.** Unchanged ranges (they depend on the photos only): clean test retake 7%, corrupted 44%.

**Policy score.** The frozen cross-validation rule now picks the **photometric TTA spread**
(out-of-fold val AURC 3.01, against 3.28 for the classifier), not the classifier.

**Abstention among gate-passed photos** (3400 estimates, 116 images): shift 4.36 -> 3.29 points
at 80% coverage (-25%, 95% CI 2.42-4.42) and 3.77 at 90% (-14%); flip rate 0.27 -> 0.27.

**Full policy** at the 80% target: corrupted test photos 44% retake, 11% consult an expert, 45%
answered (shift of answered 3.27 against 5.71 with no policy; flip rate 0.27 against 0.32).
Clean test photos: 7% retake, 22% consult, 70% answered (90% target: 12% consult, 81% answered).

**Catch rates per corruption** (share of unreliable estimates refused, all levels; final pipeline):

| corruption | unreliable | gate | gate, level 5 | full policy (80%) | shift of answered (80%) |
|---|---:|---:|---:|---:|---:|
| Gaussian blur | 25% | 86% | 98% | 92% | 1.52 |
| motion blur | 22% | 52% | 74% | 78% | 1.36 |
| defocus | 22% | 77% | 98% | 88% | 2.01 |
| sensor noise | 66% | 72% | 98% | 77% | 6.57 |
| JPEG | 17% | 45% | 86% | 69% | 1.54 |
| low resolution | 16% | 56% | 81% | 78% | 1.29 |
| over-exposure | 42% | 59% | 89% | 72% | 3.74 |
| under-exposure | 37% | 72% | 100% | 86% | 2.32 |
| colour cast | 51% | 12% | 12% | 41% | 7.61 |
| combined chain | 29% | 29% | 88% | 60% | 2.59 |

Without colour preprocessing, colour cast is the main gap: half its estimates move by more than
3.64 points, the gate catches 12% of them, the full policy 41%, and answered colour-cast
estimates still move 7.6 points on average. Sensor noise is the other weak spot (answered 6.6).

**Flips by threshold** (gate-passed, 80% coverage): 0%: 0.16, 3%: 0.14, 5%: 0.11, 10%: 0.07,
20%: 0.05. Clean test estimates: 27% exactly 0, 24% above 0 and below 5%.

Figures: `report/figures/phase6_final/`.

## Limitations

- **28% of clean test estimates are exactly 0% on diseased leaves** (possible missed mild disease).
  Abstention cannot catch this: the error is in the clean estimate itself, which is the reference.
- **Stability, not correctness.** Error is measured against the same method on the clean photo.
  Test images have no ratings, and the method is about 14 points from gold on clean photos.
- **Corruption levels are uncalibrated placeholders**, so how often the gate sends photos back
  depends on hand-set levels. The combined chain is not a measured cheap-phone model.
- **The gate is too strict on clean photos (15-19% retakes)** and too lax on compression and
  colour cast. Ranges were set per check at the 2.5th percentile; the overall false-retake rate
  was not controlled. The rule was frozen before the results and was not re-tuned.
- **"Consult an expert" is never triggered** under the frozen thresholding rule, because the
  gate alone already refuses more than the target coverage allows.
- Abstention does not reduce the decision flip rate; flips also depend on placeholder thresholds.
- The policy classifier was fitted and chosen on the same validation estimates (val AURC 1.33
  against 2.45 on test).
- The gate test set is small (23 `skip` images) and the planned non-disputed `wide` set is empty.
- **v2 is post hoc**: it was designed after seeing the v1 test results, so its test numbers are
  less trustworthy than v1's even though it was fitted on validation and evaluated once.
- v2's 5% target is too fine for 78 validation photos; the fitted gate is the observed clean range,
  and its test false-retake rate (7%) misses the target. A larger clean reference set is needed.
- v2 sends 20% of clean test photos to "consult an expert" at the 80% target (9% at 90%).
- One region model, one seed; the uncertainty scores were not timed on a phone (TODO, Phase 8).
- **Final pipeline:** abstention reduces the shift of answered estimates but not the flip rate
  (0.27 at 80% and 90% coverage), and colour cast is largely uncaught (gate 12%, policy 41%).
  The final-pipeline numbers re-use the v2 rules after two post-hoc rounds (Phase 5 v2, Phase 6 v2).
- In the final pipeline 27% of clean test estimates are exactly 0% on diseased leaves (28% with the
  Phase 5 v1 stage); the per-disease split changed (septoria 29%, bacterial leaf streak 47%).
