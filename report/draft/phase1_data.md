# Draft report section: Data (Phase 1)

Draft written 2026-11-14 from `experiments/LOG.md`, `report/dataset_versions.md`
and the tables in `report/tables/`. Numbers are as of that date. TODO marks
things still to be checked or filled in.

## Methods

**Dataset.** PlantSeg v7 (Zenodo record 17719108; Wei et al., 2024,
arXiv:2409.04038), licence CC BY-NC 4.0. v7 was chosen over v6 on 2026-10-01
(`report/dataset_versions.md`); v6 is archived and never used. PlantSeg gives
one infected-region mask per image and an official train / val / test split,
which we keep: no image changes split, images are only removed.

**Crop and classes.** Wheat, chosen on 2026-10-01 from the per-crop image
counts. Five leaf diseases are used: stripe rust, leaf rust, powdery mildew,
septoria blotch and bacterial leaf streak (black chaff). Three other PlantSeg
wheat classes (head scab, loose smut, stem rust) are excluded because they are
not leaf diseases, so "lesion area over leaf area" does not apply to them.
This gives 706 images: 480 train, 86 val, 140 test.

**Framing tags.** Every image was tagged by hand as `close_up` (one or a few
leaves, usable for severity), `wide` (plant or field shot), `non_photo`
(diagram, plate, collage) or `skip` (unusable mask). Only `close_up` images are
used for training and for the severity test set. Current counts: 639
`close_up`, 21 `wide`, 23 `non_photo`, 23 `skip`.

**How the tags were made and changed** (all changes are rows in
`data/processed/wheat_tags.csv`; the first human tag of every image is kept in
`original_tag`):
- All 706 images were first tagged by Adrija.
- An AI review (Claude, 2026-10-04) changed 23 tags (3.3%), all powdery mildew
  images whose mask covered more than 90% of the image, to `skip`
  (`report/tables/ai_review_changes.md`).
- 13 images were later re-tagged `non_photo` by Adrija: 11 found while rating
  severity in Phase 3 and 2 collages found in the gold wrong-leaf check.
- Self-agreement of the human tagging on a 30-image re-tag: 29 / 30.
- A blind second opinion by Claude on 64 images agreed with the human tag on
  only 28 (Cohen's kappa -0.006). The 36 images where it disagreed are marked
  `disputed`. Disputed images are removed from the test set and kept in
  training.

**Duplicate photos (leakage fix).** A perceptual-hash check on 2026-11-14
(`src/data/near_duplicates.py`) found 83 near-duplicate pairs among the 706
images, 48 of them across a split boundary. Test and val were kept. 70 train
images (every copy of a val or test image, and all but one copy of each
duplicate group inside train) and 2 val images (copies of test images) were
removed, listed with reasons in `configs/split_exclude.yaml`.

**Sets used for segmentation after all filters** (`close_up`; test
non-disputed; duplicates removed from train and val):

| disease | train | val | test |
|---|---:|---:|---:|
| stripe rust | 136 | 25 | 43 |
| leaf rust | 34 | 5 | 9 |
| powdery mildew | 87 | 21 | 28 |
| septoria blotch | 66 | 16 | 24 |
| bacterial leaf streak | 49 | 11 | 17 |
| total | 372 | 78 | 121 |

## Results

**The masks are coarse.** PlantSeg masks outline the infected region, not
individual lesions. A rough HSV check found that on average 55% to 74% of the
masked area is healthy-looking green tissue, depending on the disease
(`report/tables/mask_coarseness.md`). The check is an unvalidated heuristic.
This is why Phase 2 is called infected-region segmentation and why Phase 3
refines the region before computing severity.

**The official split leaks.** Before the fix, 22 of the test images and 17 of
the validation images used in Phase 2 had a copy in the training set
(`report/tables/near_duplicates.md`).

**Some disease labels are wrong.** 12 near-duplicate pairs carry two different
disease names for the same photo, mostly septoria blotch against bacterial
leaf streak and stripe rust against leaf rust. Labels were not changed.

**Masks are not reproducible.** For the 26 train / test duplicate pairs, the
two masks of the same photo agree with a median IoU of 0.83 (lowest 0.18).

## Limitations

- **One tagger.** Framing tags come from one person; the only second opinion is
  an AI one with chance-level agreement, concentrated on the `wide` and
  `non_photo` categories. The `close_up` boundary is not well defined.
- **AI involvement.** 23 tags were changed by an AI review, and the disputed
  flag comes from an AI second opinion that is known to be unreliable.
- **Duplicate check is a lower bound.** It finds resized and re-compressed
  copies only, was run on wheat only, and the cross-split pairs were confirmed
  by eye at reduced size. Some leakage may remain. Five duplicate pairs inside
  the test set were left in.
- **Label noise of unknown size.** Only label errors that a duplicate happens
  to reveal are known. Per-disease results inherit them.
- **Small classes.** Leaf rust has 9 test images and 5 validation images.
- **Web images.** PlantSeg images are scraped from the web, not taken with
  low-end phones. Phase 4 corruptions and the own-photo set (Phase 7) are the
  only links to the target phones.
- **Licence.** CC BY-NC 4.0: non-commercial use only, attribution required.
- TODO: check the PlantSeg paper and Zenodo record for any statement about
  duplicates before the final report.
