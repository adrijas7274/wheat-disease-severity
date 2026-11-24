# Experiment timeline (Phase 9 draft)

Condensed from `experiments/LOG.md` on 2026-11-24. The LOG is the full record. This file shows the order of
decisions, so a reader can check that each frozen point came before the result it protects. **Bold** marks a
freeze or a single evaluation. The tags exist in the private development repository; the public repository is a
single snapshot of `final-v1` plus later work, so it does not carry them.

| date | phase | what happened | git tag |
|---|---|---|---|
| 2026-10-01 | 0–1 | Repo set up. PlantSeg v7 chosen over v6. Wheat chosen from per-crop counts; 5 leaf diseases. | |
| 2026-10-03 | 1 | Found that PlantSeg masks are coarse infected regions, not lesions (55–74% healthy-looking). | |
| 2026-10-04 | 1 | Tagging-tool bug deleted 204 tag rows; restored from the last commit. AI tag review: 23 tags changed. Blind AI second opinion: 36 images marked `disputed` (dropped from test, kept in training). | |
| 2026-10-05 | 2 | Phase 2 plan approved. PlantVillage dropped (no wheat, no masks). DeepLabV3+ MobileNetV3 trained. | |
| 2026-10-07 | 2 | SegFormer-B0 trained (resumable training added). Paired comparison. | |
| 2026-11-01/02 | 3 | Annotation guidelines; SAM 2 tiny smoke test. Two pixel-annotation pilots discarded; gold switched to visual rating. Rater training on synthetic leaves. | |
| 2026-11-03/04 | 3 | Gold rating sessions. **Gold finished and locked.** | `gold-v1` |
| 2026-11-09 | 3 | Blind recheck of 15 images: test–retest MAE 3.64 points (the resolution limit). | |
| 2026-11-11 | 3 | Phase 3 plan saved before any method code. Leaf rule (SAM 2 tiny + min-area 2%) chosen on tuning images by blind review, **frozen**. Phase 4 click rule fixed. | |
| 2026-11-14 | 3 | Wrong-leaf check on gold outlines: 37 of 53 pass, **locked**. | `leaf-check-v1` |
| 2026-11-14 | 1–2 | Near-duplicate check: 22 test images had a copy in train. Copies removed from train/val; both models retrained and re-scored. | |
| 2026-11-14 | 3 | Colour refinement tuned on 12 tuning images (C1 beats C0 by 12.1 points). Round 2 below the change threshold, method kept, **frozen**. | `phase3-pregold-round2`, `phase3-method-v1` |
| 2026-11-14 | 3 | **Single gold evaluation:** MAE 14.35 (9.97–19.23). | |
| 2026-11-14 | 4 | Corruption benchmark on 121 test + 37 gold. Colour cast barely moves mIoU but flips most decisions. Level mapping corrected (placeholder); tables re-binned, nothing re-scored. Phase 5 redirected to the colour stage. | |
| 2026-11-16 | 5 | v1: 12 preprocessing variants; selection rule committed first; denoise + shades-of-gray + exposure selected (flip 0.32 → 0.20). | |
| 2026-11-17 | 6 | v1 gate + uncertainty + abstention, fitted on val, test once. | `phase6-v1` |
| 2026-11-17 | 6 | v2 (**post hoc**) rules committed before its single test run. | `phase6-v2-prereg`, `phase6-v2` |
| 2026-11-17/18 | 7 | PlantDoc has no wheat. Mendeley set in; NWRD unreachable and unlicensed; photos capped at 2048 px. Mendeley run: septoria detection 6% with v1 preprocessing. | |
| 2026-11-18 | 5 | v2 (**post hoc**) per-group guards committed first; result: `none` for every group. | `phase5-v2-prereg`, `phase5-v2` |
| 2026-11-18 | 6–7 | Phase 6 v2 rules re-fitted on the final colour stage; Mendeley re-run (not independent). **Pipeline frozen.** | `final-v1` |
| 2026-11-21 | 7 | JIC downloaded after the freeze. **Single independent evaluation.** | |
| 2026-11-21/23 | – | Demo, ONNX export with INT8, README, public release. | |
| 2026-11-23 | 8 | Phone leaf finders compared on tuning images only; EfficientSAM-Ti INT8 chosen (fallback MobileSAM, rule fixed before any phone timing). Browser pipeline; parity 88% same level. App built (web + APK). | |
| 2026-11-23/24 | 8 | Treatment advice from CIBRC label claims (unverified, gated). App redesign. Safety fix: only doses with an explicit unit are shown. | |
| 2026-11-24 | 9 | Report index, methods summary, this timeline. README consistency pass. | |

**Still open:**
- real-phone speed and memory test (Phase 8);
- expert check of the advice and the levels;
- native-speaker check of the translations.
