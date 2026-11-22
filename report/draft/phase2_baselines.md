# Draft report section: Baseline infected-region segmentation (Phase 2)

Draft written 2026-11-14 from `experiments/LOG.md` and
`report/tables/baselines.md`. TODO marks things still to be checked or filled in.

## Methods

**Task.** Binary segmentation of the infected region (infected against
background) on wheat leaf photos. PlantSeg masks outline the whole infected
region, not single lesions, so this is called infected-region segmentation,
not lesion segmentation. Lesion-level severity is the job of Phase 3.

**Models.** Two lightweight models that could run on a phone:
- DeepLabV3+ with a MobileNetV3-Large encoder (`segmentation_models_pytorch`,
  ImageNet weights), 4.71 M parameters.
- SegFormer-B0 (Hugging Face `transformers`, ADE20K weights), 3.71 M parameters.

**Training.** Image size 512 (longest side resized, padded to a square). Loss:
Dice plus cross-entropy. Optimiser AdamW, learning rate 1e-4, batch size 8, up
to 100 epochs, early stopping on validation IoU with patience 10, seed 42.
Augmentation: flips, random scale, crop and colour jitter only. No phone
corruptions (those are Phase 4 and 5). One run per model.

**Data.** `close_up` images of the five wheat leaf diseases, official PlantSeg
split, after removing duplicate photos from train and val (Phase 1): 372 train,
78 val, 121 test. Test excludes images with a disputed framing tag.

**Metrics.** On the test set, per image: IoU and Dice of the infected class, and
the infected-area ratio error (absolute difference between predicted and true
infected-pixel fraction). Means with percentile-bootstrap 95% confidence
intervals (1000 resamples over images, seed 42). Per-disease IoU groups test
images by their PlantSeg disease label. The two models are compared with a
paired bootstrap on the per-image IoU difference.

**Leakage check.** The models were first trained before the duplicate photos
were found. To show the effect, three sets of numbers are reported on the same
121 test images: the first models, the first models without the 22 test images
that had a copy in their training set, and the models retrained on the cleaned
training set.

## Results

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

- **SegFormer-B0 is the better baseline:** retrained test IoU 0.658 against
  0.586, paired difference +0.072 (0.052, 0.096), which excludes zero. It leads
  on every disease.
- **The leak mattered a little.** The first models scored 0.616 and 0.671 on
  these 121 images. On the 22 leaked images they scored clearly higher than on
  the rest (0.710 against 0.595 for DeepLabV3+, 0.740 against 0.656 for
  SegFormer-B0). The drop after retraining is inside the confidence intervals.
- **Hardest diseases:** powdery mildew and bacterial leaf streak, for both
  models.
- **Cost (first checkpoints, CPU, 512 px, not a phone):** DeepLabV3+ 9.24 GFLOPs,
  100 ms, 19.08 MB; SegFormer-B0 15.53 GFLOPs, 170 ms, 14.95 MB. SegFormer-B0 is
  more accurate and smaller on disk, DeepLabV3+ is faster. TODO: re-measure on
  the retrained checkpoints and after quantisation (Phase 8).
- **Model carried forward:** the retrained SegFormer-B0.
- For scale: PlantSeg's published DeepLabV3+ ResNet50 baseline is about 25 mIoU
  over all 115 classes, a different and harder task, so the two are not
  directly comparable.

## Limitations

- **Region masks, not lesions.** IoU here measures agreement with coarse
  PlantSeg region masks. A high IoU does not mean a correct severity. On the
  tuning images, the predicted region clipped to the leaf covers most of the
  leaf.
- **The reference masks are not reproducible.** Two masks of the same
  duplicated photo agree with a median IoU of 0.83 (lowest 0.18).
- **One seed per model.** Run-to-run variation was not measured, so small
  differences between columns can't be attributed to the leak alone. The
  retrained models also had 15% fewer training images.
- **Leakage may remain.** The duplicate check is a lower bound (resized and
  re-compressed copies only). Five duplicate pairs inside the test set were
  left in.
- **Per-disease numbers carry label noise** (12 known label conflicts) and small
  samples (leaf rust: 9 test images).
- **Test-set changes after the first results.** The test set went from 130 to
  123 to 121 images as non-photos and collages were found during Phase 3. Each
  change was made from the photo alone and is recorded in
  `report/tables/baselines.md`.
- **No lab-to-field comparison yet.** The plain-background against field split
  inside PlantSeg (Phase 2b) has not been done.
- **Clean web images only.** Robustness to phone degradation is Phase 4.
