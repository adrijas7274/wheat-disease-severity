# Phase 2 baselines: infected-region segmentation

Binary segmentation (infected region vs background) on PlantSeg v7 wheat
images, `close_up`-tagged, non-disputed test set. PlantSeg masks mark the
whole infected region, not individual lesions (55-75% of masked area is
still healthy-looking tissue - see `experiments/LOG.md`, 2026-10-03/04), so
these numbers describe region-level agreement, not lesion-level accuracy.
6-class (background + 5 diseases) is an optional later experiment, not run
here.

Data: 441 train / 81 val / **123 test** images (`close_up`, non-disputed test
set; 130 test images before the 2026-11-04 update below). Loss: Dice + cross-entropy. Augmentation: flip, scale, crop, colour
jitter only - no phone corruptions yet (Phase 4/5). Image size 512.
Early stopping on val IoU, patience 10. All test metrics below are
bootstrap 95% CIs (1000 resamples, seed 42) over per-image values.

## Current results after the leakage fix (2026-11-14)

**These replace the numbers in the sections below, which are kept as the record
of the first runs.** On 2026-11-14 a near-duplicate check found copies of test
and validation photos in the training set (`report/tables/near_duplicates.md`).
Test and val were kept; 70 train images and 2 val images were removed
(`configs/split_exclude.yaml`); both models were retrained with the same
settings and seed (lr 1e-4, batch 8, patience 10, seed 42). The same day two
collage images were re-tagged `non_photo`, so the test set is **121 images**
(123 before).

Three columns, all scored on the current test set
(run `experiments/20261114_102104_baselines_leakage_fix`):
- **original:** the first models, trained on 438 train images that included
  copies of 22 test images. (441 / 81 when first trained; 3 train and 1 val
  image were re-tagged afterwards.)
- **original, no leaked test images:** the same models and scores without those
  22 test images (99 left).
- **retrained:** models trained on the cleaned set (372 train, 78 val).

| metric | model | original (n = 121) | original, no leaked test images (n = 99) | retrained (n = 121) |
|---|---|---|---|---|
| overall IoU | DeepLabV3+MobileNetV3 | 0.616 (0.569-0.660) | 0.595 (0.545-0.643) | 0.586 (0.538-0.631) |
| overall IoU | SegFormer-B0 | 0.671 (0.626-0.710) | 0.656 (0.609-0.702) | 0.658 (0.612-0.700) |
| overall Dice | DeepLabV3+MobileNetV3 | 0.731 (0.686-0.769) | 0.714 (0.669-0.756) | 0.702 (0.657-0.743) |
| overall Dice | SegFormer-B0 | 0.777 (0.738-0.810) | 0.764 (0.724-0.804) | 0.765 (0.724-0.802) |
| area ratio error | DeepLabV3+MobileNetV3 | 0.036 (0.026-0.048) | 0.040 (0.027-0.055) | 0.049 (0.037-0.063) |
| area ratio error | SegFormer-B0 | 0.032 (0.023-0.043) | 0.037 (0.025-0.050) | 0.036 (0.027-0.047) |
| paired IoU difference | SegFormer minus DeepLabV3+ | +0.055 (0.037, 0.075) * | +0.060 (0.040, 0.083) * | +0.072 (0.052, 0.096) * |

\* 95% CI excludes zero.

Per-disease IoU:

| disease | model | original | original, no leaked test images | retrained |
|---|---|---|---|---|
| bacterial leaf streak (black chaff) | DeepLabV3+MobileNetV3 | 0.522 (0.427-0.619), n = 17 | 0.493 (0.394-0.581), n = 15 | 0.474 (0.347-0.599), n = 17 |
| bacterial leaf streak (black chaff) | SegFormer-B0 | 0.598 (0.483-0.713), n = 17 | 0.579 (0.452-0.698), n = 15 | 0.590 (0.483-0.692), n = 17 |
| leaf rust | DeepLabV3+MobileNetV3 | 0.748 (0.636-0.836), n = 9 | 0.795 (0.723-0.860), n = 7 | 0.691 (0.530-0.823), n = 9 |
| leaf rust | SegFormer-B0 | 0.797 (0.710-0.866), n = 9 | 0.834 (0.779-0.881), n = 7 | 0.780 (0.681-0.868), n = 9 |
| powdery mildew | DeepLabV3+MobileNetV3 | 0.542 (0.418-0.655), n = 28 | 0.511 (0.407-0.631), n = 26 | 0.517 (0.391-0.633), n = 28 |
| powdery mildew | SegFormer-B0 | 0.580 (0.470-0.685), n = 28 | 0.551 (0.456-0.657), n = 26 | 0.562 (0.438-0.676), n = 28 |
| septoria blotch | DeepLabV3+MobileNetV3 | 0.616 (0.516-0.713), n = 24 | 0.614 (0.506-0.723), n = 16 | 0.603 (0.509-0.690), n = 24 |
| septoria blotch | SegFormer-B0 | 0.686 (0.591-0.774), n = 24 | 0.688 (0.570-0.784), n = 16 | 0.675 (0.584-0.766), n = 24 |
| stripe rust | DeepLabV3+MobileNetV3 | 0.674 (0.617-0.733), n = 43 | 0.653 (0.583-0.716), n = 35 | 0.644 (0.582-0.701), n = 43 |
| stripe rust | SegFormer-B0 | 0.724 (0.676-0.772), n = 43 | 0.715 (0.659-0.770), n = 35 | 0.713 (0.665-0.758), n = 43 |

**Retraining:**

| model | epochs run | best epoch | best val IoU (78 images) | first run: best val IoU (81 images) | time/epoch |
|---|---:|---:|---:|---:|---:|
| DeepLabV3+MobileNetV3 | 27 | 17 | 0.5595 | 0.5916 | 38.6 s |
| SegFormer-B0 | 37 | 27 | 0.6145 | 0.6386 | 30.5 s |

Runs `experiments/20261114_094320_deeplabv3plus` and
`experiments/20261114_100055_segformer`, both at commit `ca1a2bd`. The val
numbers of the first run are not comparable: that val set had 17 images with a
copy in training.

**What the three columns show.**
- **The leak inflated the first results a little.** On the 22 leaked test
  images the first models scored higher than on the other 99 (IoU 0.710
  against 0.595 for DeepLabV3+, 0.740 against 0.656 for SegFormer-B0). After
  retraining, the same 22 images score 0.636 and 0.702.
- **Retrained, the overall IoU is 0.586 (DeepLabV3+) and 0.658 (SegFormer-B0)**,
  against 0.616 and 0.671 first reported on these 121 images. The drops (0.030
  and 0.013) are inside the confidence intervals of either number, so for
  SegFormer-B0 in particular the change is small. The retrained models also
  had 15% fewer training images (372 against 438), so not all of the drop is
  the removal of leakage.
- **On the 99 images that never had a training copy**, the first and the
  retrained models are close: 0.595 against 0.575 (DeepLabV3+) and 0.656
  against 0.649 (SegFormer-B0). This is the cross-check saved in the run's
  `metrics.json` (`retrained_no_leak`).
- **SegFormer-B0 is still better, by more than before.** Paired bootstrap on
  the per-image IoU difference (SegFormer minus DeepLabV3+, 1000 resamples):
  +0.072 (0.052, 0.096) retrained, +0.055 (0.037, 0.075) for the first models.
  All three intervals exclude zero.
- **Per disease**, SegFormer-B0 leads on every disease in every column. Powdery
  mildew and bacterial leaf streak stay the hardest. Leaf rust has 9 test
  images (7 without leaked images), so its numbers move a lot.
- One seed per model: differences between the original and retrained columns
  of this size could also come from run-to-run variation, which was not
  measured.

**Model used from here on:** the retrained SegFormer-B0
(`experiments/20261114_100055_segformer/best_model.pt`). The model size and
CPU cost figures further down were measured on the first checkpoints; the
architecture is unchanged, so parameters, FLOPs and file size are the same,
but they were not re-measured.

**Still not fixed:** the hash check is a lower bound, so some leakage may
remain; 5 duplicate pairs inside the test set were left in; 12 duplicate pairs
show conflicting disease labels, which affect the per-disease rows
(`report/limitations.md`).

---

# First runs (superseded by the section above)

## Training

| model | epochs run | stopped | best val IoU | time/epoch (avg, measured) | peak GPU memory |
|---|---|---|---|---|---|
| DeepLabV3+MobileNetV3 | 38 | early stop (patience 10, best @ epoch 28) | 0.5916 | 45.0s | 3857 MB |
| SegFormer-B0 | 68 | early stop (patience 10, best @ epoch 58) | 0.6386 | 35.4s | 3492 MB |

SegFormer-B0's full run was interrupted once (terminal closed mid-training,
killed at epoch 31/100, best val IoU 0.6192 at the time) - `src/train.py`
was made resumable (per-epoch checkpoints, `--resume`) as a result, and the
run above is a clean restart under the resumable version, launched as a
detached process so it survives a closed terminal. See `experiments/LOG.md`
(2026-10-07).

## Test set results (123 images, bootstrap 95% CI)

| model | overall IoU | overall Dice | infected-area ratio error |
|---|---|---|---|
| DeepLabV3+MobileNetV3 | 0.617 (0.574-0.659) | 0.732 (0.695-0.768) | 0.036 (0.026-0.047) |
| SegFormer-B0 | **0.673 (0.632-0.710)** | **0.779 (0.744-0.810)** | 0.032 (0.022-0.043) |

SegFormer-B0 outperforms DeepLabV3+MobileNetV3 on every test metric, with
overlapping-but-separated CIs on IoU/Dice (not a huge margin, but
consistent). It also trains faster per epoch despite needing more epochs
to converge, so overall wall-clock cost is comparable.

**Paired bootstrap 95% CI on the test IoU difference** (SegFormer minus
DeepLabV3+, same 123 test images, 1000 resamples over per-image
differences): **+0.056 (0.039, 0.075) - excludes zero.** SegFormer-B0's
advantage is statistically real at this sample size, not just a difference
in the two separate (unpaired) CIs above happening to not overlap much.

## Per-disease IoU (test set, bootstrap 95% CI)

| disease | n | DeepLabV3+MobileNetV3 | SegFormer-B0 |
|---|---|---|---|
| wheat stripe rust | 43 | 0.674 (0.617-0.733) | 0.724 (0.676-0.772) |
| wheat leaf rust | 10 | 0.729 (0.627-0.814) | 0.788 (0.711-0.850) |
| wheat powdery mildew | 28 | 0.542 (0.418-0.655) | 0.580 (0.470-0.685) |
| wheat septoria blotch | 24 | 0.616 (0.516-0.713) | 0.686 (0.591-0.774) |
| wheat bacterial leaf streak | 18 | 0.537 (0.439-0.633) | 0.614 (0.498-0.731) |

SegFormer-B0 leads on every disease, not just on average. Powdery mildew
and bacterial leaf streak are the hardest classes for both models - worth
remembering given powdery mildew is also the class with the worst mask
coarseness (Section: Context, and `experiments/LOG.md` 2026-10-04 large-mask
correction). Leaf rust's n=10 is small - it's the thinnest test class after
excluding disputed/non-close_up images.

## Test set change, 2026-11-04 (130 to 123 images)

During gold rating, 7 Test images were found not to be real photos and were
re-tagged `non_photo`: 3 powdery mildew, 3 septoria blotch and 1 bacterial leaf
streak. They were judged by the rater from the photo alone, with no model output
or mask on screen. The same checkpoints were re-scored without retraining (run
`experiments/20261104_175832_baselines_retest_after_retags`).

**Control:** re-scoring the original 130 images reproduced every first-reported
number exactly, including the CIs and the paired difference. The changes below
therefore come from removing the 7 images.

| metric | model | 130 images | 123 images |
|---|---|---|---|
| overall IoU | DeepLabV3+MobileNetV3 | 0.614 (0.573-0.656) | 0.617 (0.574-0.659) |
| overall IoU | SegFormer-B0 | 0.665 (0.627-0.706) | 0.673 (0.632-0.710) |
| overall Dice | DeepLabV3+MobileNetV3 | 0.729 (0.694-0.765) | 0.732 (0.695-0.768) |
| overall Dice | SegFormer-B0 | 0.770 (0.736-0.805) | 0.779 (0.744-0.810) |
| area ratio error | DeepLabV3+MobileNetV3 | 0.037 (0.026-0.048) | 0.036 (0.026-0.047) |
| area ratio error | SegFormer-B0 | 0.034 (0.024-0.045) | 0.032 (0.022-0.043) |
| paired IoU difference | SegFormer minus DeepLabV3+ | +0.050 (0.031, 0.070) | +0.056 (0.039, 0.075) |

Per-disease IoU on the 130 images:

| disease | n | DeepLabV3+MobileNetV3 | SegFormer-B0 |
|---|---|---|---|
| wheat powdery mildew | 31 | 0.545 (0.440-0.655) | 0.560 (0.449-0.668) |
| wheat septoria blotch | 27 | 0.621 (0.525-0.707) | 0.691 (0.599-0.768) |
| wheat bacterial leaf streak | 19 | 0.521 (0.421-0.611) | 0.598 (0.489-0.701) |

Stripe rust and leaf rust are unchanged, as none of their images were removed.

The conclusions don't change, and all the changes are well within the CIs. The
SegFormer-B0 gain is mostly from two removed mildew images it scored very poorly
(IoU 0.083 and 0.061, against 0.499 and 0.227 for DeepLabV3+MobileNetV3), so its
larger lead shouldn't be read as an improvement in the model.

**Not changed:** the models were not retrained, so they still reflect the training
and validation sets as tagged then. Three Training images and one Validation image
have since been re-tagged `non_photo` (the guidelines don't require retraining for
these). The other test images were not filtered by what the rater skipped, so images
skipped for blur or for having no single main leaf remain in this test set.

## Model size and inference cost (measured, CPU)

Measured directly, not assumed - see `src/compare_baselines.py`. FLOPs via
`torch.utils.flop_counter` at 512px; CPU inference is mean wall-clock time
over 20 runs (5 warmup) for one 512px image, single-threaded default
PyTorch CPU settings, on this project's dev machine (not a phone).
**Checkpoint file size is the raw PyTorch `state_dict` (.pt) size - not the
final TFLite/INT8-quantised size.** Quantisation (Phase 8) is expected to
shrink both substantially; neither model's deployability is decided by
these numbers alone, and real TFLite conversion + quantisation hasn't been
tested yet.

| model | params | FLOPs @ 512px | CPU inference (1 image) | checkpoint size |
|---|---|---|---|---|
| DeepLabV3+MobileNetV3 | 4.71M | 9.24 GFLOPs | 100ms | 19.08 MB |
| SegFormer-B0 | 3.71M | 15.53 GFLOPs | 170ms | 14.95 MB |

Not a clean win for either side. SegFormer-B0 has fewer parameters and a
**smaller checkpoint file** (14.95 MB, already under the Phase 8 <15MB
target as a raw .pt - DeepLabV3+'s 19.08 MB is already over it, pre-any
quantisation) - but needs 1.7x the FLOPs and is 70% slower on this CPU
(likely the attention mechanism's overhead vs MobileNetV3's depthwise
convolutions, which are unusually CPU-friendly). DeepLabV3+MobileNetV3 is
not simply "the lighter model" as earlier assumed without measurement -
it's lighter on compute/latency, heavier on disk. Which one wins after
TFLite/INT8 conversion is an open question for Phase 8, not decided here.

## Context

PlantSeg's own published DeepLabV3+ResNet50 baseline is ~25 mIoU over all
115 classes (full dataset, multi-class). This project's binary, 5-class,
single-crop setup is not directly comparable, but modest numbers here are
expected for the same reason: PlantSeg is a hard, in-the-wild dataset.
