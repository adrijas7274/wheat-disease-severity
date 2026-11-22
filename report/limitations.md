# Limitations notes

Running notes for the final limitations section (Phase 7).

## Gold-standard severity ratings

**Final numbers:** gold is finished at 54 / 54 and locked. Computed on
2026-11-04 from `data/annotations/rating_log.csv`. Details:
`report/tables/rating_check_final_2026-11-04.md`.

**Single rater.** All ratings come from one rater. The blind recheck below
measures self-consistency, not accuracy. A second rater was considered and
**decided against on 2026-11-14**, so there is no inter-rater agreement figure
and nothing checks this rater's bias. Every result against gold is a result
against one person's visual estimate.

### Blind recheck: the ratings are not reproducible at fine resolution

On 2026-11-09 the rater re-rated 15 randomly drawn gold images blind
(`report/tables/recheck_agreement.md`, scatter in
`report/figures/recheck/gold_vs_recheck_scatter.png`).

| metric | value (n = 15) |
|---|---|
| mean absolute difference | 3.40 pts (bootstrap 95% CI 1.80 to 5.17) |
| mean signed difference, recheck - gold | -2.20 pts |
| Lin's CCC | -0.08 (95% CI -0.38 to 0.17) |
| Pearson r | -0.14 |
| same severity level (PLACEHOLDER thresholds 5% / 20%) | 7 / 15 |
| same leaf clicked (SAM 2 from each click, automatic) | 9 / 15 |

What this means for the results:

- **Resolution limit.** A second look by the same rater differs by 3.64 points
  on average on the 14 recheck images that stay in evaluation (3.40 on all 15).
  Method errors against gold near or below 3.64 points can't be told apart, so
  no difference between methods smaller than this is claimed. The figure is
  reported beside every method result.
- **No reproducible ranking at low severity.** CCC is about 0: within the range
  the recheck covered (gold 3 to 16.5%, recheck 3 to 9%), the second ratings
  don't reproduce the order of the first. The two highest gold ratings in the
  sample (16.5% and 11.5%, both bacterial leaf streak) came back as 4.5% and
  3.5%. Most of the gold set lies in this range (46 of 54 below 20%).
- **Untested at high severity.** No recheck image had a gold rating above
  16.5%, so the recheck says nothing about repeatability for the 8 gold images
  at 20% or more.
- **Unstable estimate.** With n = 15 and a narrow range, CCC has a wide interval
  and is sensitive to single images. It is reported as measured.
- **Level agreement is threshold-bound.** Many ratings sit near the 5%
  placeholder threshold, so small differences change the level (8 of 15
  changed). The thresholds are placeholders, not validated against an agronomy
  source.
- **Lower on second look.** The recheck ratings average 2.2 points below gold.
  Which of the two is closer to the truth is unknown.

**The main leaf itself is not reproducible.** By the automatic check (each click
inside the leaf SAM 2 finds from the other click), the two clicks picked the
same leaf on 9 of 15 images. The six that failed:

| image | reading of the overlay sheet |
|---|---|
| `wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (3).jpg` | two different spikes, no leaf in the photo |
| `wheat_leaf_rust_Google_0339.jpg` | adjacent detached leaves |
| `wheat_powdery_mildew_Baidu_0206.jpg` | different objects |
| `wheat_septoria_blotch_Google_0115.jpg` | different objects |
| `wheat_stripe_rust_Baidu_0011.jpg` | recheck click on a spike |
| `wheat_leaf_rust_Google_0328.jpg` | **uncertain**: SAM 2 outlined a pustule cluster for each click, so the check can't tell |

The readings in the right-hand column are Claude's, from
`report/figures/recheck/same_leaf_check.png`. For `Google_0328` the rater could
not tell from the overlay whether the clicks are on the same leaf (2026-11-11),
so there is no confirmed visual count: it would be 9 / 15 or 10 / 15 depending
on that image, and **9 / 15 is the reported figure**. Picking a different leaf
doesn't explain the rating disagreement: on the 9 automatic same-leaf images
the mean absolute difference is 3.72 points and CCC 0.00.

**Gold exclusion.** `black_chaff (3)` is a photo of detached spikes, not a leaf,
so the main-leaf rule can't apply. It is excluded from every evaluation metric
through `annotation.gold_exclude` (decided 2026-11-11, before any method
existed). Its locked rating is unchanged. Without it the recheck gives a mean
absolute difference of 3.64 points (95% CI 2.04 to 5.46), CCC -0.07 (95% CI
-0.37 to 0.16), same level 6 / 14 and same leaf 9 / 14. It passed tagging and
the rating skip rules, so other gold images may have similar problems that
nobody has noticed.

**Consequence for the project.** Severity accuracy against gold is a secondary
result. The primary results are the Phase 4 consistency measures (severity
shift and decision flip rate between a clean photo and its corrupted copy),
which compare the model with itself and don't depend on gold.

### Rating speed

Gold ratings took a median of 5.35 s per image (mean 6.3 s, range 3.7–16.6 s,
n = 54), and 17 of 54 took under 5 s. Tuning took a median of 6.5 s (n = 15).
Pilot 3 took a median of 12.0 s (n = 4, before the slider fix). That time covers
inspecting the photo, clicking the main leaf, comparing with the diagrams and
entering a value.

We have no evidence on whether this speed affects accuracy on real photos,
because they have no true severity values to compare against. Short rating
times may mean less careful estimates.

### Clustering of ratings

The guidelines tell the rater not to snap to diagram values, but gold ratings
are bunched. Of the 54 values, 37 (69%) fall in three bands near the 5, 10 and
35% diagrams: 21 in 4.0–5.5, 10 in 8.5–9.5 and 6 in 31–35.5. Only 9 values equal
a diagram level exactly (5.0 eight times, 20.0 once). No value lies strictly
between 20 and 31. The lowest value is 3.0, so nothing was rated 0, 1 or 2%.

The real severities may be spread this way, or the diagrams may be anchoring
the rater. These data can't separate the two. If it is anchoring, the ratings
are coarser than their 0.5-point step suggests, which limits how small a model
error can be meaningfully measured against them.

Ratings are also concentrated at low severity: the median is 6.5%, and 46 of 54
are below 20%. High-severity performance rests on only 8 images.

### Skip rates and selection

32 of the 86 gold images seen were skipped (37%), and the rate differs sharply
by disease:

| disease | rated | skipped | skip rate | left in queue |
|---|---|---|---:|---:|
| stripe rust | 11 | 0 | 0% | 32 |
| leaf rust | 10 | 0 | 0% | 0 |
| powdery mildew | 11 | 13 | 54% | 7 |
| septoria blotch | 11 | 11 | 50% | 5 |
| bacterial leaf streak | 11 | 8 | 42% | 0 |

The reasons were no single main leaf (15), main leaf too blurred (10) and not a
real photo (7, tagging errors). Without the tagging errors, the rates are 48%
(mildew, 10 of 21), 42% (septoria, 8 of 19) and 39% (bacterial leaf streak, 7 of
18).

Rated mildew, septoria and bacterial leaf streak images are therefore a selected
subset: sharp photos with one clear main leaf. Results for these diseases apply
to that subset, not to all their PlantSeg photos, and comparisons with the rusts
should keep this in mind. Blurred photos in particular are under-represented in
the gold set, and those matter for the corruption work.

Bacterial leaf streak used its whole queue and met its quota on the last image.
Leaf rust has only 10 eligible images, so its quota is 10 rather than 11.

### Ratings made in two sessions

The 54 ratings were made in two sessions two days apart: 35 on 2026-11-02 and 19
on 2026-11-04.

| session | n | median s | under 5 s | median % | IQR % | max % | values ≥ 20% | in the three bands |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| first 35 | 35 | 5.3 | 13 | 5.5 | 4.5–10.25 | 57.0 | 8 | 28 (80%) |
| last 19 | 19 | 5.6 | 4 | 6.5 | 5.25–11.25 | 19.0 | 0 | 9 (47%) |

Speed barely changed. The later ratings have no high values and are less bunched
in the three bands, but this comparison can't show a change in the rater:

- **Different diseases:** the first 35 are stripe rust, leaf rust, mildew and 3
  septoria. The last 19 are 8 septoria and 11 bacterial leaf streak. Only septoria
  is in both, with too few images to compare (3 and 8).
- **Possible calibration shift:** before the second session, the rater was shown
  the tuning leaf rust photos next to their ratings, with a comment that 68%
  looked like a possible overestimate. This could have lowered later ratings.
  We can't tell how much, or whether it did at all.

The blind recheck (15 images drawn from all 54, results above) gives some
evidence on consistency across time, but not on the disease differences.

## Leaf masks and the wrong-leaf check

**The leaf rule was designed by an AI.** The rule that turns a click into a
leaf (SAM 2 tiny, `min_area`, 2%) was proposed by Claude (AI). It was chosen on
12 tuning images from outlines that Claude also judged; Adrija checked and
accepted those 29 verdicts. The margin was one image out of 12.

**The wrong-leaf check was AI-judged, then checked by the rater.** On
2026-11-14 Claude judged all 53 gold outlines from the overlays only (photo,
gold click, SAM 2 outline), before any severity was computed on gold. Adrija
checked the contact sheet (`report/figures/leaf_masks/leaf_check_sheet.png`),
added the partial-leaf rule (an outline is correct only if it covers about
three-quarters or more of the clicked leaf's visible area), had it re-applied
to the five outlines flagged as partial, and accepted the other verdicts. The
check is locked (tag `leaf-check-v1`).

| disease | kept | wrong leaf | not a leaf | duplicate | collage |
|---|---:|---:|---:|---:|---:|
| stripe rust | 8 | 2 | 1 | 0 | 0 |
| leaf rust | 5 | 4 | 0 | 0 | 1 |
| powdery mildew | 8 | 2 | 0 | 1 | 0 |
| septoria blotch | 9 | 2 | 0 | 0 | 0 |
| bacterial leaf streak | 7 | 0 | 2 | 0 | 1 |
| total | 37 | 10 | 3 | 1 | 2 |

**This is weaker than a blind human check.**
- The same AI designed the rule and judged its output, so it may share the
  rule's blind spots.
- The human check confirmed verdicts that were already visible. It is not an
  independent judgement and is open to anchoring on the AI's answer.
- The image file names (which contain the disease) were available to the AI,
  though the verdicts were made from the overlay images.
- The partial-leaf rule was written after the first pass, and "three-quarters"
  was judged by eye. On three of the four images it turned to "wrong"
  (sheet 18, 36, 49) the call depends on reading two leaf halves as one
  folded leaf, which the photo doesn't prove.
- Four borderline calls were accepted as first judged (sheet 4, 21, 31, 52).

**The gold evaluation set is small and uneven: 37 images.** 16 of the 53
checked images are out (30%), on top of the earlier exclusion. Leaf rust has 5
images left. The SAM 2 leaf rule gave a wrong leaf on 10 of the 53 checked
images, so results describe images where the leaf step worked, not all photos.
TODO: recount the severity bands (38 / 7 / 8 before the check) for the 37
images when the evaluation is run.

**Collages re-tagged late.** The two collage gold images were re-tagged
`non_photo` on 2026-11-14 (Adrija's decision), after they had been rated and
after the first Phase 2 test results. The Phase 2 test set is 121 images from
that date (123 before, 130 at first).

## Duplicate photos across PlantSeg splits

Found on 2026-11-14 with a perceptual-hash check (`src/data/near_duplicates.py`,
full list in `report/tables/near_duplicates.md`). Among the 706 wheat images
of the five classes (480 train, 86 val, 140 test) there are 83 near-duplicate
pairs, 48 of them across a split boundary.

**What leaked.**
- **Train / test:** 22 of the Phase 2 test images had a copy in the training
  set (septoria blotch 8, stripe rust 8, and 2 each for the other three
  diseases). The first Phase 2 test results were partly measured on photos
  the models had trained on.
- **Train / val:** 17 of the 80 Phase 2 validation images had a copy in
  training, so early stopping and "best val IoU" of the first models were
  affected the same way.
- **Gold:** 8 of the 37 gold evaluation images had a copy in the old training
  set.

**What was done (Adrija, 2026-11-14).** Test and val were kept. 70 training
images were removed (every copy of a val or test image, and all but one copy
of each duplicate group inside train), and 2 val images that are copies of
test images. The list with reasons is `configs/split_exclude.yaml`. Both
baselines were retrained on the cleaned set (372 train, 78 val) with the same
settings and seed. `report/tables/baselines.md` shows the first models, the
first models without the 22 leaked test images, and the retrained models.

**What is still limited.**
- **The check is a lower bound.** It finds resized and re-compressed copies.
  Crops, mirrored or rotated copies, heavily watermarked copies and different
  photos of the same leaf or field are not found, so some leakage may remain.
- **Only wheat was checked.** The other PlantSeg crops and PlantDoc have not
  been checked against these images.
- **Duplicates inside test and val were left in** (5 pairs inside test), so a
  few photos count twice in the test metrics.
- **The 48 cross-split pairs were confirmed by eye only at reduced size**, by
  Claude, on `report/figures/near_duplicates/pairs.png`.
- **Which copy is kept inside train is arbitrary** (a `close_up` one, then
  first by name). The copies can carry different masks.

**Same photo, different mask.** For the 26 train / test pairs the two PlantSeg
masks of the same photo agree with a median IoU of 0.83 (lowest 0.18; 3 pairs
at 0.95 or more). The reference masks themselves are not reproducible, which
puts a ceiling on how much a test IoU can mean.

## Disease label conflicts in PlantSeg

12 of the 83 near-duplicate pairs carry two different disease names for the
same photo (list in `report/tables/near_duplicates.md`). At least one label in
each pair is wrong, and we don't know which. **No label has been changed.**

- The conflicts are between septoria blotch and bacterial leaf streak (6
  pairs) and between the rusts (4 pairs), plus one leaf rust / septoria and
  one stripe rust / bacterial leaf streak pair.
- Six rated images are involved: four gold images
  (`wheat_septoria_blotch_blotch (22).jpg`,
  `wheat_bacterial_leaf_streak_(black_chaff)_Bing_0004.jpg`,
  `wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (25).jpg`,
  `wheat_leaf_rust_Google_0374.jpg`), one more gold image that is already
  excluded as a collage, and one tuning image
  (`wheat_bacterial_leaf_streak_(black_chaff)_Bing_0002.jpg`). Of the four,
  `Bing_0004` and `black_chaff (25)` are in the 37-image gold evaluation set.
- These are only the conflicts that a duplicate happens to reveal. Photos with
  a wrong label and no duplicate can't be found this way, so the real label
  error rate is unknown and probably higher.
- Effect: the segmentation is binary, so training is not affected by the
  disease name. Every **per-disease** number (Phase 2 per-disease IoU, gold
  results by disease, quotas per disease in the rating sets) inherits the
  label noise.

## Severity method (Phase 3), as tuned on 2026-11-14

Tuning results only (`report/tables/refinement_tuning.md`, 12 tuning images).
Gold has not been scored.

- **The method is still far from the ratings.** On the tuning images the frozen
  method (C1 on the model's region) has an MAE of 15.1 points (bootstrap 95% CI
  4.8 to 26.0), in-sample, against a rating noise of 3.64 points. It
  overestimates on average (+10.4 points).
- **A few images carry most of the error.** Three of the 12 images are off by
  about 38 to 51 points (one mildew, one septoria, one bacterial leaf streak)
  and three are within 3 points. The mean hides this split.
- **The raw regions are useless as severity.** PlantSeg's mask and the model's
  prediction, clipped to the leaf, give 75 to 78 points of error: they cover
  almost the whole leaf on most tuning images.
- **Twelve images, three thresholds.** The thresholds were chosen on 4, 5 and 3
  images per disease group. Leave-one-out MAE is 17.3 points. Two thresholds
  (necrotic 15, mildew 8) are at the edge of their grid, so the best value may
  lie outside it; the grid was fixed in advance and not extended.
- **Tuning images are validation images.** The segmentation model's early
  stopping used the validation split, which contains the tuning images. They
  were not trained on, but they are not fully independent of the model.
- **Untuned constants.** The healthy-green range, the yellow (chlorotic) range
  and the mildew lightness floor are placeholders. The green range starts at
  hue 25 (OpenCV), so pure yellow tissue counts as healthy green in C0.
- **One tuning image has a conflicting disease label**
  (`wheat_bacterial_leaf_streak_(black_chaff)_Bing_0002.jpg`, labelled septoria
  blotch in a training copy). Both labels are in the same refinement group, so
  the threshold used is the same either way.
- **The leaf is not always the leaf.** The frozen leaf rule failed on 2 of the
  12 tuning images in the leaf rule review; those images are still in the
  tuning set.

## Corruption benchmark (Phase 4), as built on 2026-11-14

- **The corruption levels are placeholders.** The five levels of each of the
  ten corruptions were set by hand and are not calibrated against photos from
  real low-end phones. "Level 3" of one corruption is not comparable with
  "level 3" of another.
- **Synthetic, applied to web images.** The corruptions are applied to PlantSeg
  photos that have already been resized and compressed by their sources.


## Gold evaluation of the severity method (2026-11-14)

Results: `report/tables/gold_evaluation.md` (37 images, one run, frozen method).

- **The method is not accurate enough to give a severity level.** Pooled MAE is
  14.35 points (95% CI 9.97 to 19.23) against a rating noise of 3.64 points.
  Level and decision agreement with the rating is 24% (PLACEHOLDER thresholds),
  below the 62% that always answering "low" would reach on these 37 images.
- **Errors go both ways.** The mean signed error is +1.2 points, so the average
  hides large over- and underestimates: 13 of the 25 images rated below 10% are
  scored "none", and the 6 images rated 20% or more are off by 27 points on
  average.
- **The region model adds almost nothing to severity.** After refinement,
  PlantSeg's region and the model's region give the same error (14.41 and
  14.35). The regions cover most of the leaf, so the colour rule decides the
  result.
- **The colour rule is the weak stage.** In the pre-gold diagnosis the three
  worst tuning images all had a correct leaf and failed in the colour stage:
  two through the chlorotic halo rule (29 and 44 points added), one because the
  whole mildew leaf is pale. A second tuning round (extended grids, optional
  halo) improved leave-one-out MAE by only 2.2 points, less than the rating
  noise, so the method was not changed.
- **The rating and the method may not count the same thing.** On the three
  diagnosed tuning photos the discoloured tissue looks much larger than the
  rating (Claude's reading of the figures in
  `report/figures/pregold_round2/`; not checked by Adrija, no rating changed).
  If the ratings count only clear lesions and the method counts all
  discoloured tissue, part of the error is a definition gap.
- **Per-disease and per-band rows are small samples** (5 to 9 images per
  disease, 6 in each of the medium and high bands).
- **One gold image has a conflicting disease label** (`black_chaff (25)`).
  Results with and without it differ by 0.2 points.
- **Three levels in practice.** The placeholder `high_max` is 100%, so "high"
  and "consult_expert" are never reached by a severity estimate.

## Corruption benchmark results (Phase 4, 2026-11-14)

Results: `report/tables/robustness.md`. In addition to the points above:

- **Stability, not correctness.** Shift, level accuracy and flip rate compare
  the method with itself on the clean image. The method is about 14 points from
  the gold ratings, and on gold its error against the rating stays at 11 to 15
  points at every corruption level.
- **Flip rates depend on the placeholder thresholds.** On clean test images the
  method's median severity is 4.2%, next to the 5% threshold, and 19% of images
  are within 3 points of a threshold.
- **The result describes the colour rule more than the models.** Both models
  flip equally often; the corruptions that change colour or brightness flip the
  most decisions.
- **The combined chain is not the worst case** (it flips fewer decisions than
  noise alone). The reason was not tested.
- **The automatic click is part of the measurement** on test images.
