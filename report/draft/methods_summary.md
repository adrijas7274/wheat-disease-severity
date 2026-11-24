# Methods summary (Phase 9 draft)

Draft written 2026-11-24 from the phase drafts (`report/draft/phase1_data.md` … `phase8_mobile.md`),
`experiments/LOG.md` and `report/tables/`. It summarises the whole study. The phase drafts hold the detail and
every number. Levels, decisions and treatment advice are **placeholders**, not validated against an agronomy
source.

## 1. Question

When a low-end phone photo of a wheat leaf is degraded, how far does the estimated disease severity move, how
often does that change the treatment decision, and can the system recognise when its estimate is unreliable and
decline to answer?

## 2. Data

- **PlantSeg v7** (Wei et al., 2024; Zenodo 17719108; CC BY-NC 4.0), wheat, five leaf diseases: stripe rust,
  leaf rust, powdery mildew, septoria blotch and bacterial leaf streak. Head and stem diseases are excluded,
  because lesion area over leaf area does not apply to them. The official split is kept; images are only
  removed, never moved.
- **Framing tags** by hand (`close_up`, `wide`, `non_photo`, `skip`). Only `close_up` images are used for
  segmentation. Test images with a disputed tag are excluded from test.
- **Leakage fix:** a perceptual-hash check found 48 near-duplicate pairs across splits. The copies were removed
  from train and val (`configs/split_exclude.yaml`) and the models retrained. Final sets: 372 train, 78 val,
  121 test.
- **Gold standard:** visual severity ratings by one rater on 54 test images, with one click on the main leaf.
  They were locked (tag `gold-v1`) before any severity method existed. A blind recheck of 15 images gives a
  test–retest MAE of **3.64 points**, used as the resolution limit everywhere. A separate tuning set of 15 rated
  validation images (12 after exclusions) is the only rated data any method was fitted on.
- **External sets, never used for training:**
  - Mendeley Wheat Leaf, Ethiopia (406 photos). Used during development, so **not independent**.
  - Bangladesh healthy leaves (250). Used only as a guard set in Phase 5 v2.
  - JIC, UK. Downloaded only after the pipeline was frozen, and evaluated once.
  - PlantDoc was planned but has no wheat.

## 3. Final pipeline (`final-v1`)

1. **Quality gate** (image only): sharpness, noise, brightness, clipped highlights and shadows, JPEG blockiness
   and minimum size. Its ranges are fitted on clean validation photos. A failure gives "retake the photo".
2. **Infected region:** SegFormer-B0 (3.7 M parameters), binary, trained with Dice + cross-entropy and standard
   augmentation. PlantSeg masks are coarse regions (55–74% of the masked area looks healthy), so this step finds
   where disease is, not the lesion pixels.
3. **Leaf:** SAM 2.1 hiera-tiny, prompted with the farmer's tap. Of its three candidates, the highest-scoring one
   covering ≥ 2% of the image is kept. In the evaluations the tap is replaced by an automatic click: the deepest
   point of the largest predicted region on the clean photo, or the image centre if there is none. This rule was
   fixed before Phase 4.
4. **Lesion pixels:** a colour rule in CIELAB inside the region, one threshold per disease group: rust a\* ≥ 10;
   septoria and bacterial streak a\* ≥ 15; mildew chroma ≤ 8 with L\* ≥ 35. Yellow tissue touching a kept
   pixel is also kept (the halo rule). The thresholds were tuned on the 12 tuning images. There is no colour
   preprocessing (Phase 5 v2).
5. **Severity** = lesion pixels on the leaf ÷ leaf pixels.
6. **Uncertainty:** the spread of the severity when the photo is made slightly brighter, darker, warmer and
   cooler before the colour rule. This needs no extra network call. Above a threshold fitted on validation, the
   answer is "consult an expert".
7. **Level and decision (placeholders):** none = 0%, low < 5%, medium < 20%, high ≥ 20%. These map to no
   action, monitor, treat and treat urgently.

**Mobile version (`final-v1-mobile`):** the same rules, with SegFormer-B0 dynamic INT8 (7.8 MB) and
EfficientSAM-Ti INT8 (17.8 MB) in place of SAM 2, ported to JavaScript and run with onnxruntime-web. It is
packaged as an offline web app and an Android APK in 23 languages.

## 4. Evaluation design

| question | data | reference | metrics |
|---|---|---|---|
| Can the network find the infected region? (Phase 2) | 121 test | PlantSeg masks | IoU, Dice, area-ratio error, per disease; bootstrap 95% CIs; paired bootstrap between models |
| Is the severity correct? (Phase 3) | 37 gold (after a wrong-leaf check) | one rater | MAE with bootstrap CI, signed error, by band; level and decision agreement |
| How much do phone faults move it? (Phase 4) | 121 test × 10 corruptions × 5 levels; 37 gold cross-check | same method on the clean photo | mIoU, severity shift, level accuracy, **decision flip rate**, leaf IoU |
| Does preprocessing make the colour stage robust? (Phase 5) | the Phase 4 grid; 250 healthy leaves as a guard (v2) | same as Phase 4 | mean shift (primary), flip rate, zero rate, healthy false severity |
| Can it refuse bad estimates? (Phase 6) | fitted on 78 val; evaluated on 121 test | same as Phase 4 | risk–coverage, AURC, risk at 80/90% coverage, retake/consult/answer shares, catch rate per corruption |
| Does it work on new field photos? (Phase 7) | Mendeley, JIC | image-level labels | share detected (> 0%), healthy false-severity rate, gate outcomes |
| Is the phone version the same method? (Phase 8) | 121 test | final-v1 | severity difference, same level, decision, gate and action |

**Corruptions** (Phase 4): Gaussian, motion and defocus blur; sensor noise; JPEG; low resolution; over- and
under-exposure; colour cast; and a combined low-res → noise → JPEG chain. Each is deterministic per (seed, type,
level, image), generated on the fly. The level parameters are hand-set, not measured on real phones.

## 5. Integrity rules

- **Frozen before evaluation:**
  - the gold ratings (`gold-v1`);
  - the leaf rule and the wrong-leaf check (`leaf-check-v1`);
  - the severity method (`phase3-method-v1`), before its **single** gold evaluation;
  - the selection rules of Phases 5 and 6 (`phase5-v2-prereg`, `phase6-v2-prereg`);
  - the final pipeline (`final-v1`), before the single JIC evaluation.
- **Change thresholds fixed in advance:** a method could replace another only if it improved by more than the
  rater's 3.64-point test–retest MAE.
- **Post-hoc rounds are labelled:** Phase 5 v2 and Phase 6 v2 were designed after earlier results were seen. Both
  were fitted on validation data only and evaluated once, and the earlier rounds are reported unchanged.
- **Logging:** every exclusion is logged with a reason. Every run folder stores its config, git commit and
  metrics.
- **Disclosed AI assistance:** an AI assistant changed 23 framing tags and gave a blind second opinion on the
  tags. It also judged the leaf-rule review and the wrong-leaf check, which the rater then checked.
  Translations and the advice table are machine-made drafts awaiting expert review.

## 6. What the evaluation cannot show

- **Stability, not correctness:** the robustness and abstention results measure stability against the method's
  own clean estimate, not correctness. Only the 37 gold images measure correctness, and they have one rater.
- **No severity error on external sets:** they have image-level labels only.
- **Untested settings:** the placeholder thresholds and the hand-set corruption levels limit every flip rate.
  Real-phone speed is unmeasured.
