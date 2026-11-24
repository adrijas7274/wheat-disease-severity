# Report material: index

Every table and figure in `report/`, with the phase, what it shows and the command that produced it. Commands
are run from the repository root. Decisions and run folders are in `experiments/LOG.md` under the date given.
Draft report sections are in `draft/`; `limitations.md` collects every known limitation.

**Status labels:** *frozen* = produced once by a frozen method and never re-run (do not regenerate for tuning);
*post hoc* = designed after earlier test results were seen; *superseded* = kept for the record, not the final
pipeline; *hand* = written by hand in a session from a logged check (no script).

Levels, decisions and treatment thresholds everywhere are **placeholders**, not validated against an agronomy
source.

## Draft sections (`draft/`)

| file | content |
|---|---|
| `methods_summary.md` | the whole method and evaluation design on two pages (start here) |
| `experiment_timeline.md` | condensed timeline of `experiments/LOG.md`: what was decided when, and the frozen tags |
| `phase1_data.md` … `phase8_mobile.md` | one section per phase: methods, results, limitations |

## Tables (`tables/`)

### Phase 1: data and tags

| table | shows | produced by | status |
|---|---|---|---|
| `mask_coarseness.md` | share of healthy-looking pixels inside PlantSeg masks (55–74%) | `python -m src.severity.mask_coarseness_check` | – |
| `tagging_agreement.md` | rater's self-agreement on framing tags (29/30) | self-check mode of the tagging tool (`src/data/tag_wheat_images.py`) | – |
| `ai_review_changes.md` | the 23 tags changed by the AI review | hand (LOG 2026-10-04) | – |
| `inter_rater_agreement.md` | blind AI second opinion vs human tags (kappa −0.006) | hand (LOG 2026-10-04); read by `src.data.add_disputed_column` | – |
| `large_mask_recheck.md` | masks covering > 90% of the image | `python -m src.data.list_large_masks` | – |
| `near_duplicates.md` | dHash near-duplicates across splits (leakage) | `python -m src.data.near_duplicates` | – |

### Phase 2: infected-region baselines

| table | shows | produced by | status |
|---|---|---|---|
| `baselines.md` | IoU, Dice, area-ratio error with CIs; before and after the leakage fix | `python -m src.train …`, `python -m src.compare_baselines`, `python -m src.rescore_after_leakage_fix` | – |

### Phase 3: gold standard, leaf masks and severity

| table | shows | produced by | status |
|---|---|---|---|
| `rater_training.md` | rater training on synthetic leaves | `python -m src.severity.rater_training` | – |
| `rating_check_2026-11-03.md`, `rating_check_final_2026-11-04.md` | rating progress and lock checks | hand (LOG 2026-11-03, 2026-11-04) | gold locked, tag `gold-v1` |
| `recheck_agreement.md` | blind recheck; test–retest MAE 3.64 points | `python -m src.severity.recheck_report` | – |
| `leaf_mask_tuning.md`, `leaf_rule_review.md` | leaf rule candidates on tuning images; blind review | `python -m src.severity.leaf_mask`, `python -m src.severity.leaf_rule_review` | rule frozen 2026-11-11 |
| `leaf_check_notes.csv` | wrong-leaf check of gold outlines (37 of 53 pass) | `python -m src.severity.leaf_check_tool` | tag `leaf-check-v1` |
| `refinement_tuning.md` | colour refinement grid on 12 tuning images | `python -m src.severity.tune_refinement` | – |
| `pregold_round2.md` | second tuning round (method not changed) | `python -m src.severity.pregold_round2` | tag `phase3-method-v1` |
| `gold_evaluation.md` | **the single gold evaluation** (MAE 14.35, CI 9.97–19.23) | `python -m src.severity.evaluate_gold --gold` | **frozen**; level columns use the old mapping |
| `gold_levels_v2.md` | gold level agreement with the current placeholder levels (22%) | `python -m src.severity.rereport_gold_levels --run experiments/20261114_174642_gold_evaluation` | re-binned only, nothing scored |

### Phase 4: corruption benchmark

| table | shows | produced by | status |
|---|---|---|---|
| `robustness.md` | 10 corruptions × 5 levels × 2 models: mIoU, severity shift, level accuracy, flip rate | `python -m src.corruptions.benchmark --experiment configs/experiments/phase4_benchmark.yaml` (re-binned with `--report-only <run>`) | – |
| `robustness_old_levels.md` | the same with the old level mapping | same run, before the mapping change | superseded |

### Phase 5: colour stage

| table | shows | produced by | status |
|---|---|---|---|
| `phase5_colour_stage.md` | 12 preprocessing variants; v1 selection | `python -m src.severity.phase5_colour_stage` | superseded by v2 |
| `phase5_v2.md` | per-group selection with guards: `none` everywhere | `python -m src.severity.phase5_v2` | **post hoc**; final (tag `phase5-v2`) |

### Phase 6: gate, uncertainty, abstention

| table | shows | produced by | status |
|---|---|---|---|
| `abstention.md` | v1, pre-registered, on the Phase 5 v1 stage | `python -m src.uncertainty.phase6 --experiment configs/experiments/phase6_abstention.yaml` | superseded (tag `phase6-v1`) |
| `abstention_v2.md` | v2 rules on the Phase 5 v1 stage | `python -m src.uncertainty.phase6_v2 --experiment configs/experiments/phase6_v2.yaml` | **post hoc**, superseded |
| `abstention_final.md` | **v2 rules re-fitted on the final colour stage** | see the README reproduce table | **post hoc**; final (`final-v1`) |

### Phase 7: external field photos

| table | shows | produced by | status |
|---|---|---|---|
| `phase7_mendeley.md` | Mendeley, Phase 5 v1 pipeline (where the septoria problem was found) | `python -m src.external.phase7 --experiment configs/experiments/phase7_external.yaml` | superseded |
| `phase7_mendeley_final.md` | Mendeley, final pipeline | `… --experiment configs/experiments/phase7_mendeley_final.yaml` | not independent |
| `phase7_jic.md` | **JIC, the one independent external test** | `… --experiment configs/experiments/phase7_jic.yaml` | **frozen**, evaluated once |

### Phase 8: export, mobile version, app

| table | shows | produced by | status |
|---|---|---|---|
| `export.md` | ONNX FP32 / INT8 size, latency, IoU | `python -m src.export` | – |
| `leaf_finders.md` | MobileSAM vs EfficientSAM-Ti vs GrabCut against SAM 2 (tuning images only) | `python -m src.mobile.compare_leaf_finders` | – |
| `mobile_parity.md` | browser / Python mobile / final-v1 agreement on 121 test images | `python -m src.mobile.parity prepare`, `node app/parity/run_parity.mjs data/mobile_parity`, `python -m src.mobile.parity compare` | – |
| `advice_sources.md`, `advice_review.csv` | CIBRC label claims, conversions, expert review sheet | `python -m src.mobile.build_advice` | **unverified** |
| `translation_review.csv`, `translation_review_howto.md` | 84 phrases × 22 languages for native-speaker review | `python -m src.mobile.review_sheet` | machine drafts |

## Figures (`figures/`)

| folder / file | shows | produced by |
|---|---|---|
| `crop_selection/` | contact sheets per candidate crop and disease (Phase 1 Part A) | exploratory, script not included (Phase 1 session, 2026-10-01) |
| `wheat_sample_overlays.png` | PlantSeg masks on 16 wheat images | `python -m src.data.wheat_dataset_stats` |
| `tag_review/` | framing-tag review sheets | `python -m src.data.build_tag_review_sheets` |
| `area_diagrams/` | standard area diagrams used in rater training | `python -m src.severity.area_diagrams` |
| `recheck/` | blind recheck and same-leaf check | `python -m src.severity.recheck_report` |
| `leaf_masks/` | leaf rule tuning, review and wrong-leaf check sheets | `src.severity.leaf_mask`, `leaf_rule_review`, `leaf_check_tool` |
| `near_duplicates/` | duplicate pairs across splits | `python -m src.data.near_duplicates` |
| `pregold_round2/` | stage-by-stage diagnosis of the worst tuning images | `python -m src.severity.diagnose_tuning`, `pregold_round2` |
| `robustness/` | metric vs level per corruption; flip-rate heatmaps (test and `_gold` cross-check) | Phase 4 benchmark |
| `phase5/` | colour-stage variants | `python -m src.severity.phase5_colour_stage` |
| `phase6/`, `phase6_v2/` | risk–coverage and gate retake rates (superseded stages) | Phase 6 v1 / v2 |
| `phase6_final/` | **final** risk–coverage and gate retake rates | Phase 6 v2 on the final stage |
| `phase7/`, `phase7_final/`, `phase7_jic/` | external severity distributions and overlays (the JIC plot keeps the generic file name `mendeley_severity.png`) | Phase 7 runs |
| `leaf_finders/` | phone leaf finders vs SAM 2 | `python -m src.mobile.compare_leaf_finders` |
| `demo/` | demo GIF and retake screenshot (JIC photos, CC BY 4.0) | made for the public release (LOG 2026-11-22/23) |
| `app/` | app screenshots (Pixel 5 emulation); `app/mockups/` the three design directions | `python app/parity/ui_test.py` |

Figures containing PlantSeg images are CC BY-NC 4.0 derivatives: see `figures/ATTRIBUTION.md`.
