# Draft report section: Cheap-phone corruption benchmark (Phase 4)

Draft written 2026-11-14 from `experiments/LOG.md` and
`report/tables/robustness.md`. TODO marks things still to be checked or filled in.

## Methods

**Corruptions.** Ten phone-style degradations, five levels each, applied on the
fly: Gaussian, motion and defocus blur, sensor noise (shot plus read noise),
JPEG compression, low resolution (downscale then upscale), over- and
under-exposure and colour cast (both in linear light), and a combined chain
(low resolution, then noise, then JPEG). Blur sizes scale with the image.
Every corruption is deterministic in (seed, corruption, level, image name).
**The level parameters are hand-set placeholders, not calibrated on real
low-end phones.**

**Pipeline under test.** For each corrupted image the whole severity pipeline
is re-run: infected region from the model, leaf from SAM 2, colour refinement
(the frozen Phase 3 method), severity = lesion pixels / leaf pixels, level and
decision from the config (**placeholder thresholds 5% and 20% and placeholder
decision mapping**).

**Leaf click.** Test images have no stored click. The click is the point
deepest inside the largest infected component that SegFormer-B0 predicts on the
clean image (image centre if none). It is reused for every corrupted version
and for both models; SAM 2 is re-run each time. The rule was fixed before the
benchmark existed. As a cross-check the benchmark is repeated on the 37 gold
images with the rater's real clicks.

**Metrics**, per model, corruption and level, with bootstrap 95% CIs over images:
- mIoU of the infected region against the PlantSeg mask (as in Phase 2);
- severity shift: mean |severity(corrupted) - severity(clean)|, in points;
- severity-level accuracy against the clean image's level;
- **decision flip rate**: share of images whose decision differs from the
  decision on the clean image;
- IoU of the SAM 2 leaf with the clean image's leaf.

The reference is the same model on the clean image, not a human rating. The
benchmark therefore measures stability, not correctness.

**Data.** 121 test images (`close_up`, non-disputed) and 37 gold images.
Models: SegFormer-B0 and DeepLabV3+ MobileNetV3, retrained after the leakage fix.

## Results

Test set, SegFormer-B0 (clean mIoU 0.658):

| corruption | mIoU, level 5 | severity shift, level 3 / 5 (points) | flip rate, level 3 | flip rate, level 5 |
|---|---:|---:|---|---|
| colour cast | 0.647 | 11.7 / 16.8 | 0.54 (0.45-0.63) | 0.67 (0.59-0.75) |
| over-exposure | 0.562 | 6.6 / 12.9 | 0.40 (0.32-0.49) | 0.60 (0.52-0.69) |
| sensor noise | 0.514 | 10.3 / 14.2 | 0.55 (0.45-0.64) | 0.58 (0.48-0.67) |
| under-exposure | 0.604 | 7.8 / 11.7 | 0.40 (0.32-0.49) | 0.55 (0.46-0.63) |
| Gaussian blur | 0.541 | 5.7 / 7.5 | 0.30 (0.22-0.39) | 0.45 (0.36-0.54) |
| defocus blur | 0.554 | 5.2 / 6.9 | 0.26 (0.19-0.35) | 0.40 (0.32-0.49) |
| motion blur | 0.575 | 3.9 / 5.1 | 0.26 (0.18-0.34) | 0.37 (0.29-0.46) |
| combined chain | 0.462 | 3.7 / 6.9 | 0.26 (0.18-0.35) | 0.36 (0.28-0.45) |
| low resolution | 0.576 | 1.7 / 4.0 | 0.17 (0.12-0.24) | 0.30 (0.22-0.38) |
| JPEG | 0.595 | 2.1 / 6.8 | 0.17 (0.11-0.24) | 0.26 (0.18-0.34) |

Flip rates use the current placeholder levels (none = exactly 0%, low below 5%, medium below 20%, high
from 20%); the numbers under the first mapping are in `report/tables/robustness_old_levels.md`.

Full tables for both models, all levels and the gold cross-check:
`report/tables/robustness.md`. Figures: `report/figures/robustness/`
(`flip_rate_heatmap.png`, `flip_rate_vs_level.png`, `severity_shift_vs_level.png`,
`level_accuracy_vs_level.png`, `miou_vs_level.png`, and `_gold` versions).

- **Segmentation accuracy hides the decision instability.** A strong colour
  cast leaves mIoU nearly unchanged (0.658 to 0.647) while 67% of decisions
  flip. Mild sensor noise (level 1) costs 0.02 mIoU and flips 49% of decisions.
- **Colour and brightness changes do the most damage**; loss of detail (JPEG,
  low resolution) does the least.
- **Noise raises the estimate, colour cast, over-exposure and blur lower it.**
- **Both models flip equally often**, although DeepLabV3+ loses far more mIoU
  under noise (0.586 to 0.290). Severity is decided by the colour rule and the
  leaf, not by the region model.
- **The combined chain flips less than noise alone** (0.36 against 0.58 at
  level 5). TODO: test whether the JPEG step is what smooths the noise.
- **Gold cross-check:** with real clicks colour cast is again the worst (level 5:
  colour cast 0.81, Gaussian blur and under-exposure 0.59, over-exposure 0.57,
  sensor noise 0.51). The error against the rating
  stays between 11 and 15 points at every level.

## Limitations

- Corruption levels are placeholders; "level 3" of two corruptions is not the
  same amount of real-world degradation, so the ranking of corruptions is
  indicative only. TODO: calibrate on real low-end phone photos.
- The severity method under test is about 14 points from the gold ratings
  (resolution limit 3.64). Stability of a poor estimate is still worth
  measuring, but the flip rates describe this method, not severity estimation
  in general.
- The flip rate depends on the placeholder thresholds. The method's median
  clean severity on test is 4.2%, next to the 5% threshold, which raises the
  flip rate. The severity shift in points does not depend on the thresholds.
- With the placeholder thresholds the decision is one-to-one with the level, so
  the flip rate equals 1 minus the level accuracy.
- The automatic click and the SAM 2 leaf are part of what is measured: on test
  the leaf itself changes under corruption (IoU with the clean leaf down to
  0.46 for the combined chain).
- Synthetic corruptions on web images that were already resized and compressed.
- One seed per model; 37 images in the cross-check.
