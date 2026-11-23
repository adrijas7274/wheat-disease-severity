# Experiment Log

Running log of experiments: date, name, what changed, key metrics, conclusion.

---

## 2026-10-01 — Phase 0: setup

**What changed:** Created repo structure (`configs/`, `data/`, `notebooks/`, `src/`,
`experiments/`, `tests/`, `app/`, `report/`), `requirements.txt`, `.gitignore`,
`README.md`. Added `src/utils/`: `seeding.py` (RNG seeding), `config.py` (YAML
loading), `git.py` (commit hash for provenance), `experiment.py` (timestamped
experiment dirs + JSON metric logging), `check_env.py` (environment check CLI).
Added `configs/config.yaml` with `crop: "tbd"` (to be chosen in Phase 1),
placeholder severity thresholds, and a placeholder decision mapping — both
explicitly marked as unvalidated against any agronomy source.

**Key metrics:** N/A (no models trained yet).

**Conclusion:** No code yet to validate against real data. Phase 0 is scaffolding
and passes its own tests; see summary in conversation for `pytest` / `check_env` output.

---

## 2026-10-03 — Observation: PlantSeg masks are region-level, not lesion-level (not just rust)

**What changed:** No code. Observed while manually tagging wheat images that
PlantSeg's lesion masks outline the whole infected leaf region, not
individual lesions within it. First noticed on rust diseases (stripe rust,
leaf rust), where the mask covers the blotchy/streaked area around
pustules rather than the pustules themselves - but the same pattern also
shows up in **wheat septoria blotch** masks, which outline the whole
infected leaf/lesion patch rather than the individual necrotic spots within
it. This likely applies across classes, not just rust. Either way,
`mask_pixels / leaf_pixels` overestimates true severity, since the masked
region includes healthy-looking tissue between the actual diseased spots.

**Key metrics:** See `report/tables/mask_coarseness.md` for a quantified
per-class estimate (fraction of masked area that is healthy-green by HSV
thresholding, computed 2026-10-03 on close_up-tagged images).

**Plan (not started - still tagging):** refine lesions inside the existing
PlantSeg region, e.g. colour-based pustule/lesion segmentation restricted to
the masked area, and validate the refined masks against a small
hand-annotated set before trusting severity numbers derived from them.
Needs to land before Phase 3 (severity) relies on raw PlantSeg mask area as
the severity numerator.

**Conclusion:** Flagging now so it isn't forgotten; no implementation yet per
explicit instruction - revisit once tagging is done.

---

## 2026-10-04 — Bug: global Backspace handler silently deleted 204 tag rows

**What changed:** Fixed a bug in `src/data/tag_wheat_images.py`'s keyboard
handler. It listened for every `keydown` on the whole page with no check for
text-input focus. The disease/list `gr.Dropdown`s are searchable (they have
a filter text box); typing or backspacing inside one to filter the list was
also caught by the page-level listener, and Backspace maps to "Undo", which
deletes the most recently written tag row from `wheat_tags.csv` one at a
time. Result: ~204 tag rows silently deleted, discovered when post-review
stats showed septoria blotch/bacterial leaf streak back to mostly
"untagged" despite having been completed earlier. Fix: the handler now
returns early when `e.target` is an input/textarea/contenteditable element.

**Recovery:** restored `data/processed/wheat_tags.csv` from the last commit
(`e8a730a`, 706 rows, the complete original 5-class tagging) via
`git checkout e8a730a -- data/processed/wheat_tags.csv`. This is a full
recovery of the original tagging work with zero loss, because it had
already been committed before review mode was used.

**Key metrics:** 204/706 rows (29%) affected before recovery; 0 after.

**Not recoverable:** any tag changes made during the review-mode session
itself were never committed anywhere before the bug wiped them, so they are
genuinely gone - not restorable from git or anywhere else. If real changes
were made during review (e.g. retagging some of the 24 large-mask powdery
mildew images), they need to be redone.

**Conclusion:** Root cause was a missing input-focus guard on a page-global
key listener, not a logic error in the undo/tagging functions themselves
(those behaved exactly as designed - the bug was triggering them
unintentionally). Fixed and should not recur.

---

## 2026-10-04 — AI-assisted tag review pass (disclose in report)

**What changed:** At Adrija's request, Claude reviewed (not Adrija) three
groups of already human-tagged wheat images and corrected tags where
warranted, following docs/tagging_guidelines.md. `wheat_tags.csv` gained
provenance columns (`original_tag`, `tag`, `tag_source`, `review_reason`) so
every human tag is preserved unchanged alongside any AI correction - see
src/data/migrate_tags_schema.py and src/data/wheat_tags.py.

- **Large-mask powdery mildew (24 images, >90% mask area):** 23 changed to
  `skip` (mask found to be a box over the whole canopy/background/multiple
  leaves, not tracing a single leaf), 1 left unchanged. Full list:
  `report/tables/ai_review_changes.md`.
- **Stripe rust (228) and bacterial leaf streak (83), full review:** 0
  changes - none showed clearly whole-plant/tillers/field framing with
  small leaves; all left as close_up per "when in doubt, keep."
- **Second-rater check:** Claude independently re-tagged a balanced sample
  (30 random close_up + all 23 original wide + all 11 original non_photo +
  0 original skip = 64 images) with tags hidden, then compared to the
  human's original tags. **Agreement: 28/64 (43.8%), Cohen's kappa: -0.006**
  (chance-level). Disagreement is concentrated almost entirely on the wide
  category: in 19/36 disagreements Claude called close_up where the human
  said wide, and in 10/36 Claude called close_up where the human said
  non_photo - i.e. Claude applied a visibly stricter threshold for both
  "wide" and "non_photo" than the human did. Full breakdown and per-image
  reasons: `report/tables/inter_rater_agreement.md`.

**Key metrics:** 23/706 (3.3%) tags changed by AI review. Updated counts:
652 close_up, 21 wide, 10 non_photo, 23 skip (0 untagged). Mask coarseness
on the final close_up set: stripe rust 62.1%, leaf rust 74.1%, powdery
mildew 74.2%, septoria blotch 55.4%, bacterial leaf streak 62.0% mean
healthy-green fraction inside the mask (`report/tables/mask_coarseness.md`).

**For the thesis report:** state plainly that 23 of 706 tags (3.3%) were
AI-reviewed and corrected, not purely human-tagged, and that the inter-rater
kappa (-0.006) indicates the close_up/wide/non_photo boundary is genuinely
ambiguous between raters as currently written - not that either rater was
"wrong." This is a real limitation of the current guidelines, worth
discussing rather than hiding: tightening the wide/non_photo criteria with
concrete visual examples would likely raise agreement in a future pass.

**Conclusion:** The large-mask correction pass found a real, substantial
problem (96% of the worst mask-quality offenders needed correcting) and the
guidelines' tie-breaker worked well there. The second-rater check surfaced a
different, equally real problem: low inter-rater reliability on the
wide/non_photo categories specifically. Both findings are kept, not
smoothed over.

**Correction (2026-10-04, from Adrija):** Claude's blind inter-rater tags
should be treated as a **low-confidence second opinion, not ground truth**.
Two concrete reasons: Claude called 10 of the 11 original non_photo images
close_up (near-total miss on that category), and Claude's own earlier
qualitative estimate (crop-selection phase, 30-image contact sheet) put
bacterial leaf streak at ~35-40% wider/medium framing, while Claude's full
83-image review of the same class - same reviewer, same guidelines - found
zero wide-worthy images. These two Claude-produced numbers contradict each
other, so Claude's own framing judgment is not stable across viewing
contexts. The `disputed` column in `wheat_tags.csv` (added 2026-10-04,
true where original_tag and Claude's blind tag disagreed) should be read
accordingly: as "worth a human recheck," not as "Claude's tag is probably
more correct." original_tag and tag are unaffected by this correction.

---

## 2026-10-05 — Phase 2 plan approved; PlantVillage dropped

**What changed:** No training code yet. Adrija approved the Phase 2 plan
with three changes, now reflected in the project plan:

1. **PlantVillage dropped entirely** from the project (removed from
   the project plan section 4's dataset table and from Phase 2). Reason: it has no
   wheat images and no segmentation masks, so it can't serve either role it
   was listed for (lab→field motivation figure, or any ablation) for this
   project's actual crop. The lab→field domain-gap story is covered two
   other ways instead: (a) within PlantSeg itself, comparing
   plain-background/detached-leaf images against field images - this needs
   a small tagging or heuristic pass to tell them apart first, so it's
   deferred to **Phase 2b**, not done now; (b) the clean-vs-degraded gap
   already planned for Phase 4 (corruption benchmark).
2. **Binary infected-region segmentation is the main Phase 2 baseline**,
   not 6-class. Metrics: overall IoU/Dice for the infected class,
   per-disease IoU (test images grouped by their known disease, from
   metadata - not predicted), infected-area ratio error, all with
   bootstrap 95% CIs. 6-class (background + 5 diseases) stays available as
   an optional later experiment, not the headline number.
3. **Phase 6 quality-gate test set clarified**: all non-disputed `wide`
   images (every split) plus all `skip` images are fair game, since the
   segmentation model never trains on either - added to the project plan Phase 6.

**Key metrics:** N/A (planning only).

**Conclusion:** No code invalidated by this - WheatSeverityDataset,
tagging tool, and all Phase 1 tooling are unaffected. This just scopes
Phase 2's actual training run, which starts next.

---

## 2026-10-05 — Phase 2: DeepLabV3+MobileNetV3 baseline trained

**What changed:** Built the Phase 2 pipeline (src/models/segmentation.py,
src/severity/{losses,metrics}.py, src/data/severity_transforms.py,
src/train.py, src/evaluate.py), all binary infected-region segmentation per
the approved plan. Found and fixed two real bugs before any real run: (1)
the venv's torch was a CPU-only wheel (`pip install -r requirements.txt`
alone never gets CUDA on Windows - see the new note in requirements.txt),
silently reporting `CUDA available: False` despite a working RTX 3050; (2)
`drop_last=False` on the train DataLoader produced a trailing batch of size
1 at 441 train images / batch 8, which crashes BatchNorm in training mode -
fixed with `drop_last=True` on the train loader only (val/test use
`model.eval()`, which doesn't have this problem).

Verified with `--debug` (CPU, ~20 images, 1 epoch) for both models, then one
real epoch of each on GPU to measure real timing/memory before committing
to a full run (both comfortably fit in 6GB - see table below).

Also found: a full `pytest` run that should take ~10s instead took 3 hours
once `src/data/severity_transforms.py` (imports `albumentations`) existed -
albumentations does an unbounded DNS-lookup version check at import time,
and this environment's network is restricted. Fixed by setting
`NO_ALBUMENTATIONS_UPDATE=1` before the import, not relying on a shell env var.

Trained DeepLabV3+MobileNetV3 to completion: early-stopped at epoch 38
(best at epoch 28, patience 10), ~45s/epoch average, ~3857MB peak GPU
memory.

**Key metrics:** best val IoU 0.5916. Test set (130 images, bootstrap 95%
CI): overall IoU 0.614 (0.573-0.656), Dice 0.729 (0.694-0.765),
infected-area ratio error 0.037 (0.026-0.048). Per-disease IoU ranges from
0.521 (bacterial leaf streak, n=19) to 0.729 (leaf rust, n=10 - small
sample, wide CI). Full table: `report/tables/baselines.md`.

**Conclusion:** Comfortably above the ~0.25 mIoU PlantSeg's own
multi-class/115-class baseline gets (not directly comparable - binary vs
multi-class, 5 vs 115 classes, single crop - but directionally reassuring
that a binary infected-region task on a narrower label set is tractable at
this scale). SegFormer-B0 training next.

---

## 2026-10-07 — SegFormer-B0 interrupted, train.py made resumable, finished

**What changed:** SegFormer-B0's full training run was killed when the
terminal was closed by accident (Bash background jobs die with the shell
session that spawned them - this is a real limitation of how training was
being launched, not a training bug). It had reached epoch 31/100, best val
IoU 0.6192 at epoch 24, with no resumable state saved (only `best_model.pt`,
weights-only, no optimizer/epoch/history).

Fixed properly rather than just restarting blind: `src/train.py` now saves
a full checkpoint every epoch (model + optimizer state + epoch count + best
val IoU + early-stopping counter + history) to `last_checkpoint.pt`, and
accepts `--resume <path>` to continue with identical state - verified with
an actual save-1-epoch, resume, continue-2-more-epochs cycle in debug mode
before trusting it. Since the interrupted run itself had no checkpoint
richer than weights-only, it was restarted from scratch under the new
resumable code rather than faked-resumed from incomplete state.

Relaunched as a **detached Windows process** (`Start-Process`, not a Bash
background job) so it survives a closed terminal or ended session -
confirmed detached by checking its parent process had already exited while
training kept running.

**Key metrics:** SegFormer-B0: 68 epochs, early-stopped (patience 10, best
@ epoch 58), best val IoU 0.6386, ~35.4s/epoch, ~3492MB peak GPU memory.
Test set (130 images, bootstrap 95% CI): overall IoU 0.665 (0.627-0.706),
Dice 0.770 (0.736-0.805), infected-area ratio error 0.034 (0.024-0.045) -
**beats DeepLabV3+MobileNetV3 on every metric, including every per-disease
IoU.** Full table: `report/tables/baselines.md`.

**Conclusion:** SegFormer-B0 is the stronger Phase 2 baseline on accuracy.
"DeepLabV3+MobileNetV3 is lighter" (written here on first pass) was an
**unverified assumption, and wrong on at least one axis**: measured on
2026-10-07 (see below), SegFormer-B0 actually has the smaller checkpoint
file (14.95MB vs 19.08MB) and fewer parameters, while DeepLabV3+MobileNetV3
needs fewer FLOPs and is faster on CPU. Neither is simply "the lighter
model" - which one deploys better is a Phase 8 question (TFLite/INT8
conversion untested), not decided here. Both baselines are done; Phase 2
training is complete. Not starting Phase 3.

---

## 2026-10-07 — Phase 2 measured comparison: paired CI + model cost

**What changed:** Added `src/compare_baselines.py`: a paired bootstrap 95%
CI on the test IoU difference between the two models (same 130 test
images, bootstrapped over per-image differences - not just comparing the
two models' separate unpaired CIs), plus measured (not assumed) parameter
count, FLOPs at 512px (`torch.utils.flop_counter`, no new dependency), CPU
inference time, and checkpoint file size for both models. Corrected the
unverified "DeepLabV3+ is lighter" claim above with these numbers.

**Key metrics:** Paired IoU difference (SegFormer - DeepLabV3+): +0.050
(0.031, 0.070) - **excludes zero**, so SegFormer-B0's advantage is
statistically real at this sample size. Model cost: DeepLabV3+MobileNetV3
4.71M params / 9.24 GFLOPs / 100ms CPU inference / 19.08MB checkpoint;
SegFormer-B0 3.71M params / 15.53 GFLOPs / 170ms CPU inference / 14.95MB
checkpoint. Full writeup: `report/tables/baselines.md`.

**Conclusion:** SegFormer-B0 wins on accuracy (now with a paired
significance test backing it, not just two CIs that happen not to overlap
much) and on checkpoint size; DeepLabV3+MobileNetV3 wins on FLOPs and CPU
latency. These are raw PyTorch numbers - TFLite/INT8 conversion (Phase 8)
could change the ranking on any of these axes and hasn't been tested yet.

---

## 2026-11-01 — Phase 3 start: annotation guidelines, SAM 2 tiny smoke test

**What changed:** Phase 3 plan approved (see `docs/annotation_guidelines.md`,
committed e581bac): gold set of 54 test images (11 per disease, all 10 for
leaf rust - flagged low-n), 15-image tuning set from val, 5-image pilot from
train; pooled severity MAE is the primary gold metric. Installed SAM 2:

- Package: `sam2==1.1.0` (PyPI sdist), built with `SAM2_BUILD_CUDA=0` and
  `--no-build-isolation` against the existing torch 2.5.1+cu121 (first
  attempt failed because the venv had no `wheel` package; installing it fixed
  the build). torch was verified unchanged afterwards.
- Checkpoint: `sam2.1_hiera_tiny.pt`, from
  `https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt`,
  156,008,466 bytes, **SHA-256
  `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`**.
  Stored at `data/checkpoints/sam2/` (gitignored). Model config
  `configs/sam2.1/sam2.1_hiera_t.yaml` (inside the sam2 package).

Smoke test (`python -m src.severity.sam2_smoke_test`, run
`experiments/20261101_113015_sam2_smoke_test/`): 5 pilot images (train
split, one per disease), one positive click each at a pixel inside the
PlantSeg region (smoke test only - not used to make any mask).

**Key metrics (RTX 3050 6GB Laptop):** model load 4.05s; weights 288.7MB
VRAM; **peak VRAM 596.8MB allocated / 836.0MB reserved**; image encode
0.138s/image, click → mask 0.011s (means over images 2-5; image 1 includes
CUDA warm-up: 0.583s / 0.277s).

**Conclusion:** SAM 2 tiny fits easily in local VRAM and is fast enough for
interactive clicking. Single-click output is ambiguous as expected (a click
on a stripe-rust lesion returned the whole leaf), so the tool relies on
positive/negative clicks plus the wand and brush. **Data issue found:** the
septoria pilot image `wheat_septoria_blotch_blotch (77).jpg` is a painted
illustration, not a photo, yet it is tagged `close_up` and non-disputed, so
some non-photos may remain under `close_up`. Added "not a real photo" as a
logged skip reason in the annotation tool.

**Update (same day):** the "not a real photo (mis-tagged)" skip reason is
approved. Using it now also appends a re-tag row to `wheat_tags.csv`
(`tag = non_photo`, `tag_source = human_annotation`, `original_tag` and
`disputed` kept). Annotation queues are now frozen to
`data/annotations/queues/<set>.csv` on first start: without this, a
re-tag would shrink the eligible list, and the seeded shuffle of the
shorter list would reorder the whole queue partway through the set.
**Follow-up owed after the gold set:** if any test images were re-tagged,
re-run the Phase 2 test evaluation for both baselines and record the
change in `report/tables/baselines.md`.

---

## 2026-11-01 — Pilot 1 discarded, tool fixes, pilot 2 set up

**What happened:** Pilot 1 (5 train images) produced only one real lesion
mask (stripe rust: 13.7 min, broad brush strokes looser than the
guidelines). Leaf rust and septoria had their lesion outlines drawn into
the *leaf* mask (step selector left on "leaf"). Powdery mildew and
bacterial leaf streak had fragmented multi-leaf SAM leaf masks and no
lesions. 4 of 5 were marked incomplete without reaching the 10-min cap. The
septoria image (a painted illustration) was saved instead of skipped.
**No usable time-per-image estimate came out of it.**

**What changed:**
- Tool: big coloured step banner with an on-screen checklist per step; a
  "Leaf done → Step 2" button (switches the click mode to Wand); Save
  refused on step 1, refused with an empty lesion mask unless "No visible
  lesion on main leaf" is ticked (new `no_lesion` log column); leaf
  fragmentation check (largest connected piece < 80% of the leaf → warning
  + "no single main leaf" skip pre-selected; new `leaf_largest_part` log
  column); "Incomplete" locked until the lesion cap is reached (checked
  server-side too) and reset on every new image; scroll-to-zoom /
  drag-to-pan on the click view (CSS transform; click → pixel mapping
  stays exact because Gradio uses the transformed bounding box); display
  copy raised to 2048 px (JPEG).
- Data: froze the pilot/tuning/gold queues (pilot 1 ran on the
  pre-freezing tool version), removed pilot 1's 5 images from the frozen
  pilot queue so pilot 2 takes the next seeded image per disease, deleted
  pilot 1's log rows and masks, then logged a retroactive "not a real
  photo" skip for `wheat_septoria_blotch_blotch (77).jpg` and re-tagged it
  `non_photo` (`tag_source = human_annotation`). It's a **training** image,
  so the Phase 2 *test* evaluation isn't affected. The Phase 2 models were
  trained with it in the `close_up` training set (noted, no retraining).

**Pilot 2 images:** wheat_stripe_rust_Baidu_0459.jpg,
wheat_leaf_rust_Google_0009.jpg, wheat_powdery_mildew_Bing_0271.jpg,
wheat_septoria_blotch_google_septoria (6).jpg,
wheat_bacterial_leaf_streak_(black_chaff)_Baidu_0245.jpg.

---

## 2026-11-02 — Pilot 2 discarded; gold standard switched to visual rating

**What happened (pilot 2, 2026-11-01, 4 of 5 images saved):** no usable
masks and no usable time-per-image figure.
- Bacterial leaf streak (`..._Baidu_0245.jpg`) was never annotated.
- Leaf masks were made mostly with the magic wand, although the guidelines
  say SAM + brush. Every leaf mask came out in 236-662 disconnected pieces
  (largest piece 22% / 39% / 51% / 80% of the mask). The fragmentation
  check only warns, and all 4 were saved anyway.
- Stripe rust (`Baidu_0459.jpg`) is a **4-panel collage**: the leaf mask
  spans leaves in all four panels plus a thumb. The lesion mask is
  **empty** with `no_lesion` ticked, despite obvious orange stripes and
  676 s spent on the lesion step (over the 10-min cap, `incomplete` false).
  The brush work was either lost before saving or the box was ticked to
  get past the empty-mask refusal. Cause not confirmed.
- Leaf rust, powdery mildew and septoria: the lesion masks spill onto other
  leaves, stems and background (septoria came closest, but it also marks a
  second leaf). Logged severities 0.81 / 0.46 / 0.67 are meaningless. The
  powdery mildew image shows mildew on a **stem**, with broad leaves that
  may not be wheat, so it should probably have been skipped.
- Times: 16.1 min for stripe rust (leaf 4.8 + lesion 11.3), 0.5-1.4 min for
  the other three. The wand-only images are fast because the masks are wrong.

**Conclusion:** two pilots in a row have failed to produce usable pixel
masks with this tool. Pixel-level gold masks for rust pustules, pycnidia
and diffuse mildew aren't achievable at acceptable quality and time for 54
images by one annotator. Pilot 2's log rows and masks are kept as they are
in `data/annotations/` (old mask tool's log, not used for anything).

**Decision (Adrija):** switch the gold standard from pixel masks to
**visual severity estimation**, aided by standard area diagrams (SADs),
which is the usual way plant disease severity is rated by eye. New design,
full details in `docs/annotation_guidelines.md`:
- Rating tool (the mask tool's code is kept but retired): the image only,
  with zoom and pan. No PlantSeg mask and no model output is shown. One click
  on the main leaf (coordinates stored), then severity % (0-100). Skip
  reasons as before plus "collage / multi-panel image". Collage and
  not-a-real-photo skips re-tag the image `non_photo` (original tag kept).
  Time per image is logged.
- Synthetic SADs (wheat-leaf outline, lesions at exactly 1, 2, 5, 10, 20,
  35, 50 and 75% of leaf area, in rust, blotch and mildew styles) are
  generated by our own script and shown as a reference panel in the tool.
- Evaluation: each method's severity is computed on the leaf SAM 2 finds
  from the stored click. Methods A (PlantSeg outline clipped to that leaf),
  B (model region) and C (refined lesions) are compared against the rating.
  Primary metric: pooled severity MAE with a bootstrap 95% CI. Severity-level
  agreement and decision agreement are also reported.
- Self-consistency: 15 random gold images re-rated blind (was 5 re-annotated
  masks).
- Same frozen queues and splits: tuning 3 per disease (val), gold 54 (test).

**Built (same day):** `src/severity/rating_tool.py` (UI) +
`src/severity/rating_core.py` (logic), log at
`data/annotations/rating_log.csv`; `src/severity/area_diagrams.py`
generates the diagrams into `report/figures/area_diagrams/` (measured
coverage = target to within one pixel, see `coverage.csv`). Recheck n set to
15 in config. The rating pilot skips images already seen in the mask-tool
pilots. Tests: 178 passed. Pilot 3 (rating, 5 train images) not yet run.

**Decisions (same day, before pilot 3):**
- **Wrong-leaf check**, fixed before any gold rating: once gold ratings
  are locked, each gold image is shown with only the rater's click + SAM's
  leaf outline (no severities, no lesion masks). Images marked "wrong leaf"
  are **excluded from evaluation and the count is reported**. Added to
  `docs/annotation_guidelines.md` (tool not built yet).
- **Manual re-tag:** `wheat_stripe_rust_Baidu_0459.jpg` (Training) ->
  `non_photo` (collage / multi-panel image, seen in mask-tool pilot 2),
  `tag_source = human_annotation`, `original_tag = close_up` and
  `disputed = false` kept. Training image: Phase 2 models were trained with
  it in the `close_up` set (noted, no retraining; test set unaffected).

**Rating tool functional check (same day, after pilot 3):** browser-driven
end-to-end check (headless Chromium via Playwright, in a throwaway venv, not
a project dependency) against a scratch instance with its own log, tags copy
and queues of training images never used in any pilot. The real log, tags
CSV and queues were verified byte-identical afterwards. Two bugs found and
fixed:
- **Refused actions blanked the photo.** Any refused save/skip/load (no
  click, no severity, no name, value outside 0-100, recheck locked) raised
  `gr.Error`, and Gradio then covers *every output of that event* with an
  "Error" overlay: the photo disappears and clicks stop registering until
  each overlay is closed. Now a warning toast is shown and nothing on screen
  changes. Range checking (0-100) moved from Gradio's Number to our own
  validation for the same reason.
- **Number box could save a stale value.** With Gradio's default
  `trigger_mode="once"`, slider events fired while one was still running
  were dropped, so after a fast slider move the number box (which is what
  gets saved) lagged behind the slider (seen: slider 14.5, number 13). Now
  `trigger_mode="always_last"`, and Save also refuses if the number box and
  slider differ by more than 0.25 (one slider step is 0.5).
  **Pilot 3 was rated with the old code**, so if the slider was moved
  quickly before saving, a logged value could differ from what was on the
  slider. Not checkable after the fact.
Verified after the fixes (87 browser checks, all pass): clicks map to the
right original pixel within 1 px unzoomed, zoomed x3 and x6.2 after panning,
and on small (177-400 px) images, and the tool's marker is drawn exactly
under the cursor. Drag-to-pan never registers a click, zoom survives marker
redraws, number <-> slider sync in both directions, pause time is excluded
from `rating_s`, all 5 skip reasons are logged, only collage /
not-a-real-photo re-tag (`original_tag` kept), recheck stays locked until
gold is finished, then it's blind, can't be skipped and doesn't overwrite
gold. Unit tests: 178 passed.

---

## 2026-11-02 — Pilot 3 caveats, rating tool additions, rater training mode

**Pilot 3 caveat:** all 5 pilot 3 ratings (2026-11-02, 08:15-08:16 UTC) were
made **before the slider fix** (commit a69f0e6). A fast slider move just
before Save could have logged a value that lagged behind the slider. This
can't be checked after the fact. Pilot only (training images), not used in
any evaluation.

**Bing_0016 re-logged as a collage skip:** `wheat_stripe_rust_Bing_0016.jpg`
(Training, pilot 3) is a 2-panel collage that was rated (14.0%) instead of
skipped. A skip row ("collage / multi-panel image") was appended to
`data/annotations/rating_log.csv` on Adrija's instruction (the latest row
wins, so the rating is replaced; the original row stays in the append-only
log). This re-tagged it `non_photo` (`tag_source = human_annotation`,
`original_tag = close_up` and `disputed = false` kept). The pilot's stripe
rust slot is open again, so the tool serves the next stripe rust image in the
frozen pilot queue. Phase 2 models were trained with this image in the
`close_up` training set (noted, no retraining).

**What changed:**
- Old mask tool (port 7860) stopped.
- Small photos are enlarged for display to 1600 px on the long side (bicubic,
  display only), since the browser shrinks big images but never enlarges
  small ones. Clicks are divided by the same scale, so logged coordinates
  stay in original pixels.
- A rating above 75% (the highest diagram) needs a second Save of the same
  value. A changed value asks again.
- Reminder above the severity box: "Count only lesion/pustule area on the
  main leaf, not the green tissue between spots."
- **Rater training tab** (`src/severity/rater_training.py`): 15 synthetic
  SAD-style leaves per set (5 each rust/blotch/mildew, shuffled, random
  left-right flip), hidden severities drawn **log-uniformly** from
  0.5-60% (rounded to 0.5%), so low severities get as much practice as
  high ones (a linear draw would put about 90% of leaves above 5%). True
  value = measured lesion share, exact to one pixel. After each leaf: true
  value + error. At the end: MAE, mean signed error (over/under) and a
  per-style breakdown, appended to `report/tables/rater_training.md`.
  Repeatable with a new random set. Doesn't read or write any rating log.

**Checks:** unit tests 187 passed. The browser check was re-run on a
scratch instance (own log, tags copy, queues and training report), **103 of
103 checks pass**. Clicks land on the right original pixel within 1 px:
unzoomed, at 3x and 6.2x zoom after panning, and on small images (177-400
px, now shown enlarged 4-7x). The tool's marker is drawn under the cursor
every time. Also checked: the >75% confirmation (incl. asking again after
a change), the reminder line, and a full 15-leaf training set (hidden value
not shown before rating, feedback, no double submit or skipping ahead, end
summary, report appended, rating log untouched, repeat starts a new set).
Real log, tags CSV and queues verified byte-identical afterwards.

**Rating workflow setup (same day, before tuning/gold):** Set preselected
= tuning and Rater prefilled ("adrija"), from the new `annotation.ui`
config section. When tuning is finished the tool shows a message and
switches to gold automatically, with the next gold image already loaded.
Big progress counter ("Gold: 12 / 54 rated", skips shown separately, plus a
progress bar). Gentle break reminder every 20 images (saves + skips) per
session. No file names, split names, PlantSeg masks, model output or
pipeline details on screen: only the photo, the disease's lesion
definition, the click marker and the synthetic diagrams. Checked in the
browser on scratch instances: workflow check 19/20 (the one failure was my
image-type filter flagging Gradio's own inline SVG icons, not a tool
problem); regression check 103/103. Unit tests 190 passed. Real log, tags
CSV and queues byte-identical afterwards. Note: the pilot's stripe rust slot
(reopened by the Bing_0016 skip) is left unrated; the pilot is timing-only.

## 2026-11-03 — Rating check after tuning + gold session 1

**What:** Checked `data/annotations/rating_log.csv` with the tool's own
progress logic. Full report: `report/tables/rating_check_2026-11-03.md`.

**Key numbers:**
- Tuning finished: 15/15, no skips.
- Gold **not finished: 35/54**. Septoria is 3/11, bacterial leaf streak is
  0/11. 17 skips (13 mildew, 4 septoria). The recheck isn't open yet.
- Time per image: median 5.9 s (tuning) and 5.2 s (gold). All 67 rows took
  9.2 min of wall clock. Pilot 3 median was 12.5 s.
- Ratings cluster near the diagram levels (5, 10, 35).
- The 5 "not a real photo" gold skips re-tagged 5 Test images to `non_photo`.
  The Phase 2 test metrics predate this.

**Conclusion:** Gold must be finished before Phase 3 method work or
evaluation. Method building and tuning have not started.

## 2026-11-04 — Rating log under version control; limitations notes

**What changed:**
- `.gitignore` exception added. `data/annotations/rating_log.csv` and the
  frozen queues (`data/annotations/queues/*.csv`) are now tracked. The queues
  can't be rebuilt, because re-tagging changes what `build_queues` produces.
  The rating log is committed after each rating session from now on.
- New `report/limitations.md`: rating speed, clustering and the powdery mildew
  skip rate (interim, gold at 35 / 54).
- Corrected `report/tables/rating_check_2026-11-03.md`: the clustering counts
  are 14, 8 and 6, not 11, 7 and 5. No ratings changed.

**Tuning leaf rust check:** the 3 photos were shown to Adrija next to the
ratings (68, 24, 20%). The review result is pending and no ratings were changed.
`wheat_leaf_rust_Google_0251.jpg` (rated 24%) is a multi-panel A–F plate.
Flagged for Adrija to decide; collages are a listed skip reason.

**Conclusion:** gold is still 35 / 54. Method building hasn't started and waits
until gold is finished and committed.

## 2026-11-04 — Tuning leaf rust review decisions (Adrija)

- `wheat_leaf_rust_Google_0251.jpg` (tuning, rated 24%) is a multi-panel A–F
  plate. A skip row ("collage / multi-panel image") was appended to the rating
  log on Adrija's instruction. The latest row wins and the original row stays.
  It is re-tagged `non_photo` (`tag_source = human_annotation`, `original_tag =
  close_up` kept). Tuning is now 14/15. The slot goes to the next image in the
  frozen queue, `wheat_leaf_rust_Google_0000.jpg`, which Adrija will rate after
  finishing gold. Phase 2 ran before this re-tag (noted, no retraining).
- `wheat_leaf_rust_Bing_0046.jpg` (tuning, rated 68%): rating unchanged, but it
  **may be an overestimate**. **Open decision, to be made before tuning: keep or
  exclude this image, with the reason logged here.**

## 2026-11-04 — Preparing the GitHub remote

**Decision (Adrija):** git history is kept as it is, with no rewrite. The 28
figure files derived from PlantSeg v7 stay in the repo. CC BY-NC 4.0 allows
sharing them with attribution in a private, non-commercial repo. Credit is in
the new `report/figures/ATTRIBUTION.md`.

**Raw image check:** no file under `data/raw` (15,548 images and masks) or
`data/archive` (22,916) is in any commit, compared by git blob hash against all
213 committed blobs. A committed control file matched, so the check works. Both
folders are gitignored.

**Remote:** empty private repo `adrijas7274/crop-severity` created, `origin` set.
Not pushed yet; the push waits until the rating session is finished.

## 2026-11-04 — Gold finished and locked

**What:** Final check of the rating log. Full report:
`report/tables/rating_check_final_2026-11-04.md`. `report/limitations.md` now
has the final numbers.

**Key numbers:**
- Gold 54 / 54, 32 skips (37% of the 86 seen): mildew 54%, septoria 50%,
  bacterial leaf streak 42%, both rusts 0%. Tuning 15 / 15. Recheck not started.
- Gold time per image: median 5.35 s, and 17 of 54 under 5 s.
- Clustering: 37 of 54 in the bands 4.0–5.5, 8.5–9.5 and 31–35.5. Median 6.5%.
- First 35 vs last 19: median 5.3 vs 5.6 s and 5.5 vs 6.5%, max 57 vs 19%, in the
  bands 80% vs 47%. This is confounded by disease mix (septoria is the only
  overlap, 3 and 8 images) and by the rater having seen the tuning leaf rust
  review, including a comment that 68% might be high, before the second session.

**Gold lock (Adrija's instruction):** no edits from now on except through the
logged recheck. Tag `gold-v1`; `annotation.gold_locked` makes the tool refuse
gold saves and skips; a test checks the gold rows against `annotation.gold_sha256`.
The earlier rating tool process was stopped, so an old tab can't write to gold.

**Still open:**
- Keep or exclude `Bing_0046` before tuning, with the reason logged.
- 7 Test images were re-tagged `non_photo`, so the guidelines require the Phase 2
  test evaluation to be re-run.
- Recheck (15 images), then the wrong-leaf check.

**Conclusion:** method building and tuning have not started.

## 2026-11-04 — First push to the private repo

Corrected the `.gitignore` header comment to match CC BY-NC 4.0. Recomputed the
final rating numbers from the log; they match `report/limitations.md` and
`report/tables/rating_check_final_2026-11-04.md`, so neither changed. Pushed
`master` and tag `gold-v1` to private repo `adrijas7274/crop-severity`. The blind
recheck is for a later session. Method building and tuning have not started.

## 2026-11-04 — Bing_0046 excluded from tuning; Phase 2 re-run; evaluation plan bands

**Tuning exclusion (Adrija's decision):** `wheat_leaf_rust_Bing_0046.jpg` is
excluded from tuning. *(This first reason was replaced; see the next entry.)* Reason as given: outlier at 68% against a leaf rust median
of about 5%, likely overestimate; tuning images are not used for scoring. The
rating stays at 68% in the log. Listed in `annotation.tuning_exclude`. The slot
isn't refilled, so tuning has 14 usable images and 2 for leaf rust (20, 7.5%).

**Caveat, for the record:** the median of about 5% is the **gold** leaf rust median
(5.25%), so a gold statistic informed a tuning-set decision. No gold image, method
output or score was used in tuning by this, and no method exists yet, so the effect
should be small. It is still worth stating if the viva asks about separation between
tuning and gold.

**Phase 2 re-run:** run `20261104_175832_baselines_retest_after_retags` (commit
da966d6). Same checkpoints, no retraining, test set 130 -> 123 images after 7 re-tags.
- Control: re-scoring the original 130 images reproduced all stored numbers exactly.
- DeepLabV3+MobileNetV3: IoU 0.614 -> 0.617, Dice 0.729 -> 0.732, area error
  0.037 -> 0.036.
- SegFormer-B0: IoU 0.665 -> 0.673, Dice 0.770 -> 0.779, area error 0.034 -> 0.032.
- Paired IoU difference: +0.050 (0.031, 0.070) -> +0.056 (0.039, 0.075).
- The run printed a NOTE for both models from an exact-equality check that was too
  strict. Images in both sets differ by at most 5e-5 IoU, likely numerical noise from
  different batches. The check now uses a tolerance and raises on a real difference.
  This doesn't affect the results, so the run wasn't repeated.
- Also removed "widest CIs" from the leaf rust sentence in `baselines.md`. It was
  already wrong before this update: powdery mildew's CIs are wider.

**Evaluation plan:** severity MAE will also be reported by gold rating band: low
(< 10%), medium (10% to < 20%), high (>= 20%), with 39, 7 and 8 images. High is flagged
low-n, and medium is just as small.

**Conclusion:** SegFormer-B0 stays the stronger baseline; the removal changes no
conclusion. The next step is the blind recheck (a later session), then the method.

## 2026-11-04 — Bing_0046 exclusion reason replaced

The exclusion of `wheat_leaf_rust_Bing_0046.jpg` from tuning stands, and its rating
stays at 68%. **Current reason (Adrija):**

> 68% is far above the other leaf rust tuning ratings (20% and 7.5%), and my early
> rater-training sessions showed a strong overestimation bias on rust (about +36
> points), so this rating is likely an overestimate. Tuning images are not used for
> scoring.

**Why it changed:** the first reason referenced a gold statistic (the gold leaf rust
median of about 5%), and a tuning decision shouldn't depend on gold. It was replaced
with one that uses only tuning ratings and rater training on synthetic leaves. The
first reason stays in the entry above. The exclusion itself was first decided with
that gold statistic in mind, and changing the wording doesn't undo that.

**Figures behind the reason (`report/tables/rater_training.md`, 2026-11-02), rust
signed error:** +19.10 (08:57), +35.80 (09:00), +4.00 (09:03), n = 5 each. The +36 is
the second session. The third session, the last before `Bing_0046` was rated at 11:01,
showed a much smaller rust bias, so training supports the reason less directly than
the +36 alone suggests.

## 2026-11-09 — Blind recheck done; self-consistency and same-leaf check

**Recheck:** 15 gold images re-rated blind by Adrija (17:00-17:02 UTC, median 5.7 s
per image; gold median was 5.4 s). The 15 names match `pick_recheck` (seed 42).
Gold rows untouched (digest test passes). Report: `python -m src.severity.recheck_report`
-> `report/tables/recheck_agreement.md`, `report/figures/recheck/`.

**Agreement (n = 15):**
- Mean absolute difference 3.40 pts (bootstrap 95% CI 1.80 to 5.17). Mean signed
  difference recheck - gold = -2.20 pts.
- Lin's CCC -0.08 (95% CI -0.38 to 0.17); Pearson r -0.14.
- Same severity level (PLACEHOLDER thresholds 5% / 20%): 7 / 15.
- Range: gold 3 to 16.5% (SD 3.7), recheck 3 to 9% (SD 1.6). All recheck ratings are
  under 10%. The two highest gold ratings (16.5%, 11.5%, both bacterial leaf streak)
  came back as 4.5% and 3.5%.

**Same leaf (SAM 2 hiera tiny, one positive point, best of 3 masks; "same" = each
click inside the other click's leaf):** 9 / 15 automatic. Looking at the overlay sheet:
- Genuinely different objects (5): `black_chaff (3)` (two different spikes on a white
  background, not leaves), `leaf_rust_Google_0339` (adjacent detached leaves),
  `powdery_mildew_Baidu_0206`, `septoria_blotch_Google_0115`, `stripe_rust_Baidu_0011`
  (recheck click on a spike).
- SAM artefact (1): `leaf_rust_Google_0328`, both clicks on the same leaf, but SAM
  outlined a pustule cluster for each, so the masks don't overlap.
- So visually 10 / 15 same leaf. The automatic count (9 / 15) is the reported one;
  the visual reading is Claude's and needs Adrija's confirmation.

**Different leaves don't explain the disagreement:** on the automatic same-leaf
subset (n = 9) MAD 3.72, CCC 0.00; visual subset (n = 10) MAD 3.40, CCC 0.05.

**Noted, no action taken:** `black_chaff (3)` is a photo of detached spikes, which is
not a leaf. It is in gold (rated 5.5%). Whether it should be excluded under the
"not wheat leaf disease" rule is Adrija's decision; gold is locked, so any exclusion
would go in the evaluation config with a logged reason, not into the log.

**Conclusion:** the absolute differences are small (about 3 pts), but within this
narrow 3-17% range, the rater's ratings don't reproduce their ranking: CCC is about 0.
With n = 15 and a narrow range, CCC is unstable; it is still the honest number and
should go in the limitations. The wrong-leaf check is still to come. Method
building and tuning have not started.

## 2026-11-11 — Recheck decisions: gold exclusion, evaluation plan changes

All decisions here are Adrija's, made before any Phase 3 method exists.

**Gold exclusion.** `wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (3).jpg`
is excluded from evaluation via `annotation.gold_exclude` in `configs/config.yaml`.
Reason (Adrija): photo of detached spikes, not a leaf, so it violates the main-leaf
rule. Its gold rating (5.5%) and recheck rating stay unchanged in the locked log;
the gold digest test still passes. Evaluated gold set: at most 53 images (bacterial
leaf streak 10), before the wrong-leaf check. Low band 39 -> 38.

**Same-leaf count.** 9 / 15 automatic is the main figure. `wheat_leaf_rust_Google_0328.jpg`
is recorded as uncertain: Adrija could not tell from the overlay whether the two
clicks are on the same leaf, so Claude's earlier "10 / 15 visual" reading is
unconfirmed and is not reported as a count.

**Recheck without the excluded image (n = 14), computed with the report's own
functions and the config seed:** MAD 3.64 pts (95% CI 2.04 to 5.46), signed -2.36,
CCC -0.07 (95% CI -0.37 to 0.16), Pearson r -0.13, same level 6 / 14, same leaf
9 / 14. The n = 15 figures in `report/tables/recheck_agreement.md` are unchanged.

**Evaluation plan changes (`docs/annotation_guidelines.md`):**
- Resolution limit: test-retest MAD 3.4 pts, CCC about 0. Reported beside every
  method result; no claimed difference between methods smaller than this.
- Phase 4 (clean-vs-corrupted severity shift and decision flip rate, no gold
  needed) is the primary contribution. Severity accuracy against gold is secondary.
- Optional second rater added: classmate does rater training, rates the 54 gold
  images blind; inter-rater agreement reported; mean of both raters as reference.
  Not yet decided or scheduled. Open point: what to do where the two raters click
  different leaves.

**Also:** recheck results added to `report/limitations.md`; test added that every
`gold_exclude` name is a finished gold rating.

**Open:** which figure is the resolution limit for claims, 3.40 (all 15 recheck
images, as measured) or 3.64 (the 14 that stay in evaluation). The plan states
3.40 and gives both. Wrong-leaf check still to do. Method building and tuning
have not started.

## 2026-11-11 — Phase 3 plan saved before any method code

`docs/phase3_plan.md` holds the Phase 3 method plan with Adrija's decisions. At this
commit there is no leaf-mask, refinement, tuning or evaluation code.

**Decisions (Adrija):**
- Resolution limit is **3.64 pts** (n = 14 evaluated recheck images); 3.40 (all 15)
  is mentioned once. This settles the open point in the previous entry. Guidelines
  and limitations updated.
- C0 fallback: C1 is used only if it beats C0 on tuning MAE by more than 3.64 pts.
- App: the farmer taps the leaf. Phase 8 task added: test a phone-sized promptable
  segmentation model, report size and latency.
- Phase 4 click rule, fixed before Phase 4: centre of the largest predicted infected
  component on the clean image, or the image centre if none; same click for every
  corrupted version; cross-check on gold images with the real clicks. Added to
  the project plan Phase 4.
- Second rater: undecided, to be settled before work order step 4.

**Not yet confirmed by Adrija (Claude's proposals, plan section 7):** how "largest"
and "centre" are computed, which model's prediction gives the click, and that SAM is
re-run on each corrupted version.

## 2026-11-11 — Phase 3 step 1: leaf mask rules on the tuning set

**What ran:** `python -m src.severity.leaf_mask` on the 14 tuning images (SAM 2 hiera
tiny, stored click, 3 candidates). Experiment `20261111_134339_leaf_mask_tuning`.
Table `report/tables/leaf_mask_tuning.md`, sheet `report/figures/leaf_masks/tuning_rules.png`.
No gold image was processed and no severity was computed.

**Result:** the two rules chose different candidates on 13 of 14 images.
- `best_score` leaf covers under 2% of the image on 5 images (0.0%, 0.1%, 0.6%, 0.8%,
  1.7%): SAM picked a small part near the click.
- `largest_containing_click` leaf covers 15 to 68% on those 5, but on many images its
  outline spreads over several leaves or background.

**Claude's reading of the sheet (needs Adrija's check, not a measurement):**
`best_score` looks like one whole leaf on about 7 of 14 (4, 5, 8, 9, 10, 12, 13) and
`largest_containing_click` on about 4 of 14 (4, 6, 13, 14). Neither rule is usable as
it stands.

**Noted, no action taken:** tuning images 1 (`wheat_stripe_rust_Bing_0054.jpg`) and 11
(`..._google_black_chaff (6).jpg`) look like photos of spikes, not leaves, the same
problem as the gold exclusion. Whether to exclude them from tuning is Adrija's decision.

**Decision pending (Adrija):** the prompting rule. No rule has been written to the
config. Refinement and tuning have not started.

## 2026-11-11 — Leaf rule review set up: 2 models x 2 rules, blind

Decisions are Adrija's unless marked. Nothing below touches a gold image.

**Tuning exclusions:** `wheat_stripe_rust_Bing_0054.jpg` and
`wheat_bacterial_leaf_streak_(black_chaff)_google_black_chaff (6).jpg` excluded from
tuning. Reason (Adrija): spikes, not leaves, same rule as the gold exclusion. Ratings
unchanged. Tuning set is now 12 images. The wrong-leaf check gains a "not a leaf"
option so the same rule reaches gold (guidelines updated; the tool is not built yet).

**Phase 4 click confirmed:** SegFormer-B0 prediction on the clean image; point deepest
inside the largest predicted infected component (distance transform), image centre if
none; same click reused; SAM re-run on every corrupted version. Written into
`docs/phase3_plan.md` section 7 and the project plan.

**Second SAM 2 model:** `sam2.1_hiera_base_plus.pt` from
`https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_base_plus.pt`,
323,606,802 bytes, **SHA-256
`a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5`**, config
`configs/sam2.1/sam2.1_hiera_b+.yaml`. Base+ was chosen over small because it fits the
GPU (RTX 3050 Laptop, 6144 MiB) with room to spare. Small was not run.

**VRAM and speed** (`experiments/20261111_150149_leaf_rule_candidates`, 12 tuning
images, one click each, `torch.cuda` peak figures):

| model | peak allocated MiB | peak reserved MiB | median s per image |
|---|---:|---:|---:|
| tiny | 596.8 | 838.0 | 0.15 |
| base+ | 808.0 | 1076.0 | 0.30 |

Time covers `set_image` plus one prediction, excludes model loading and image
reading, and is from one run.

**Minimum share for `min_area`: 2% of the image** (Claude's choice, as asked, set
before the review). On the 12 tuning images the `best_score` masks split into a small
group and the rest in both models: tiny has three at or below 1.7% (0.0, 0.8, 1.7) and
its next smallest is 3.0%; base+ has two (0.8, 1.7) and its next smallest is 2.6%.
2% sits in that gap. That the small group are fragments and not leaves is Claude's
reading of the earlier sheet, not a measurement.

**Review:** 12 images x 4 combinations = 48 outlines, 29 distinct (identical masks are
judged once and credited to each combination that produced them). Order shuffled with
the config seed, model and rule names hidden, key in a gitignored file. Verdicts go to
`data/annotations/leaf_rule_review_log.csv` (tracked).

**Decision rule, fixed before the review:** most "yes" wins. Ties go to tiny over
base+ (smaller, already in use), then `best_score` over `min_area` (the rule already in
the guidelines). The winner is frozen in the config before any gold image is processed.

## 2026-11-11 — Leaf rule review: AI-judged, checked by Adrija

**Change of reviewer (Adrija's instruction):** the 29 outlines were judged by Claude
(AI), not by Adrija. **Adrija checked the contact sheet and agreed with all 29
verdicts (2026-11-11), with no overrides.** The check was done before the key was
opened or the report run, so it was blind to model and rule names.

**How it was judged:** from the overlay images only, in the shuffled review order,
with the screen's criteria (yes = the outline covers the clicked leaf, all of its
visible part, and little else). `key.json` and the report were not opened before or
after judging, so the counts per combination are still unknown to everyone.

**Limits on the blindness:** Claude wrote the review code, chose the 2% minimum share,
and had earlier seen the tiny-model `best_score` outlines and the candidate area
figures for these images (`report/tables/leaf_mask_tuning.md`, the candidates run).
So some outlines could be recognised from memory even without the key. An AI judging
outlines produced by rules it helped choose is weaker evidence than the blind human
review that was planned.

**Verdicts:** 21 yes, 8 no. Rows are in `data/annotations/leaf_rule_review_log.csv`
with rater `claude (AI)`. Overrides are appended as new rows under Adrija's name, and
the latest row per outline counts.

**Borderline calls (sheet numbers):** 7 yes (outline runs a little past the leaf on
the left), 13 no and 24 yes (same leaf; both include pieces of other leaves, larger in
13), 21 yes (ragged gap at the top of the leaf), 22 and 28 yes (one narrow blade held
in the hand).

**Sheet:** `report/figures/leaf_masks/leaf_rule_review_sheet.png`, made by
`python -m src.severity.leaf_rule_review sheet`. It shows no model or rule names.

## 2026-11-11 — Leaf rule frozen: SAM 2 tiny + min_area (2%)

**Report** (`report/tables/leaf_rule_review.md`), 12 tuning images, verdicts by Claude
(AI), all 29 checked and accepted by Adrija:

| combination | yes | no |
|---|---:|---:|
| tiny + best_score | 9 | 3 |
| tiny + min_area | 10 | 2 |
| base+ + best_score | 9 | 3 |
| base+ + min_area | 9 | 3 |

**Winner: tiny + `min_area`,** by most "yes"; the tie-break was not needed.

**Frozen in `configs/config.yaml`** (`sam2.leaf_rule: min_area`,
`sam2.leaf_min_area_share: 0.02`, checkpoint tiny), with a test. No gold image had
been processed. `leaf_from_click` now reads the rule from the config.

**How strong this is:** the margin is one image out of 12, so the four combinations
are close and this review can't separate them reliably.
- tiny + `min_area` differs from tiny + `best_score` on 3 images: it fixes two
  fragment outlines (`powdery_mildew_Bing_0173`, `leaf_rust_Google_0000`) and breaks
  one (`stripe_rust_Baidu_0168`, where it takes most of the photo).
- Base+ did not beat tiny, so the larger model is not used.
- Images every combination failed: `powdery_mildew_Bing_0096` (a segment of the leaf).
  `stripe_rust_Baidu_0204` failed only with base+.
- The frozen rule still failed on 2 of 12 tuning images. If gold behaves the same way,
  the wrong-leaf check will exclude a share of the gold images of that order; with
  n = 12 that share is very uncertain.

**Next:** work order step 2, the wrong-leaf check on gold (tool not built yet).

## 2026-11-11 — Step 2: wrong-leaf check tool built; check not started

**Tool:** `src/severity/leaf_check_tool.py` (`prepare`, `serve`, `summary`). It shows
only the photo, the gold click and the SAM 2 leaf outline. It reads no severity,
PlantSeg mask or model output. Verdicts: correct leaf, wrong leaf, not a leaf.
Order shuffled with the config seed, saved after every answer, Back one, resumes at
the first unchecked image.

**Prepared:** 53 evaluated gold images (54 minus `annotation.gold_exclude`), leaf from
the stored gold click with the frozen rule (SAM 2 tiny, `min_area`, 2%). Run
`experiments/20261111_153322_leaf_check_prepare`. Leaf masks saved to
`data/leaf_masks/gold/` (gitignored) so the evaluation uses exactly the outlines that
get checked. `prepare` refuses to run again once the check log exists.

**Tested on a scratch copy** (never the real log): each of the three buttons, Back
one, resume in a new session, and the finish screen after 53 answers.

**Rule in force (Adrija, 2026-11-11):** no severity is computed on any gold image until
this check is finished and committed. None has been. Claude has not looked at the
gold outlines.

**Log:** `data/annotations/leaf_check_log.csv` (tracked, does not exist yet).

## 2026-11-14 — Step 2: wrong-leaf check judged by Claude (AI); awaiting Adrija's check

**Who:** at Adrija's request, Claude (AI) judged all 53 gold outlines from the
overlays only (photo, gold click, SAM 2 outline). No severity, lesion mask,
PlantSeg mask or model output was computed or looked at. Rater in the log:
`claude (AI)`. The leaf rule being checked was also designed by Claude. This is
weaker than a blind human check (`report/limitations.md`).

**Provisional verdicts** (`data/annotations/leaf_check_log.csv`):

| disease | correct | wrong | not a leaf |
|---|---:|---:|---:|
| stripe rust | 8 | 2 | 1 |
| leaf rust | 8 | 2 | 0 |
| powdery mildew | 10 | 1 | 0 |
| septoria blotch | 10 | 1 | 0 |
| bacterial leaf streak | 8 | 0 | 2 |
| total | 44 | 6 | 3 |

**For Adrija's check:** contact sheet `report/figures/leaf_masks/leaf_check_sheet.png`
(`python -m src.severity.leaf_check_tool sheet`, new step), notes with a one-line
reason in `report/tables/leaf_check_notes.csv`: 10 borderline calls (sheet numbers
4, 18, 21, 24, 25, 31, 32, 36, 49, 52), 6 clear exclusions, 4 other notes.

**Also seen:** sheet images 12 and 15 are the same photo under two names; images 9,
35 and 50 are collages. Nothing was changed because of this.

**Second rater: decided no (Adrija, 2026-11-14).** Gold is single-rater; recorded in
`docs/phase3_plan.md` section 6, the guidelines and `report/limitations.md`.

**Status:** nothing committed, exclusions not locked, until Adrija confirms the sheet.
No severity has been computed on gold.

## 2026-11-14 — Step 2 finished: wrong-leaf check checked by Adrija and locked; 37 gold images

**Adrija's decisions after seeing the contact sheet:**
- **Partial-leaf rule (new):** an outline is correct only if it covers roughly
  three-quarters or more of the clicked leaf's visible area. Added to the guidelines.
  Re-applied by Claude to the five outlines flagged as partial: sheet 18, 25, 36, 49
  -> wrong; 24 stays correct. One-line reasons in `report/tables/leaf_check_notes.csv`.
- **Duplicate:** `wheat_powdery_mildew_Google_0263.jpg` (sheet 15) is the same photo as
  `wheat_powdery_mildew_Bing_0214.jpg` (sheet 12). The later one in the gold queue
  (position 76 vs 57) is excluded.
- **Collages:** `wheat_leaf_rust_Google_0358.jpg` (sheet 9) and
  `wheat_bacterial_leaf_streak_(black_chaff)_Google_0141.jpg` (sheet 50) excluded by the
  existing collage rule. Not re-tagged `non_photo` (that would change the Phase 2 test
  set; open).
- All other verdicts accepted as judged by Claude. Second rater: no.

**Final counts (53 checked images):**

| disease | kept | wrong leaf | not a leaf | duplicate | collage |
|---|---:|---:|---:|---:|---:|
| stripe rust | 8 | 2 | 1 | 0 | 0 |
| leaf rust | 5 | 4 | 0 | 0 | 1 |
| powdery mildew | 8 | 2 | 0 | 1 | 0 |
| septoria blotch | 9 | 2 | 0 | 0 | 0 |
| bacterial leaf streak | 7 | 0 | 2 | 0 | 1 |
| total | 37 | 10 | 3 | 1 | 2 |

**Locked:** `annotation.leaf_check_locked: true`, `leaf_check_sha256` (digest of the
latest verdict per image, checked by a test), tag `leaf-check-v1`. The tool refuses new
verdicts. `gold_exclude` now has 4 names, with `gold_exclude_reasons` for the three new
ones. `leaf_check_tool.evaluated_gold_rows` returns the 37 images. No severity has been
computed on gold.

**Conclusion:** the gold evaluation set is 37 images, with only 5 for leaf rust. The
check was AI-judged and human-checked, which is weaker than a blind human check
(`report/limitations.md`).

## 2026-11-14 — Near-duplicate check across splits: 22 Phase 2 test images have a copy in train

**What:** `python -m src.data.near_duplicates` (new, with tests). dHash (64 bits, at most
6 apart) plus a 32 x 32 thumbnail test, on all 706 wheat images of the five classes
(480 train, 86 val, 140 test, all tags). Report: `report/tables/near_duplicates.md`,
pair sheet `report/figures/near_duplicates/pairs.png`. Run
`experiments/20261114_093458_near_duplicates`. No dependency added.

**Found:** 83 pairs in 71 groups; 48 cross a split boundary.
- Within gold: 1 pair (the one already known).
- Tuning / gold: 0.
- Train / test, both in the Phase 2 sets: 26 pairs, 22 distinct test images of 123
  (septoria 8, stripe rust 8, bacterial leaf streak 2, leaf rust 2, mildew 2).
- Train / val: 18 pairs, 17 distinct val images of 80.
- Val / test: 2 pairs. Within one split: 35 pairs (30 in train).
- 8 of the 37 gold evaluation images have a copy in train.
- 12 pairs have two different disease labels for the same photo.
- Masks of the 26 train / test copies: median IoU 0.83, lowest 0.18.

**Could affect:** every Phase 2 test number in `report/tables/baselines.md` (probably
optimistic), early stopping on val, and Phase 3 methods that use the trained model on
gold. **Nothing changed yet (Adrija's instruction).** Decision needed on what to do.

## 2026-11-14 — Leakage fix: duplicates removed from train and val, two collages re-tagged

All decisions here are Adrija's.

**Exclusions** (`configs/split_exclude.yaml`, one reason per image, written by
`python -m src.data.near_duplicates --write-exclusions`; `configs/config.yaml` points to it
through `data.split_exclude_file`):
- **Train, 70 images removed:** every image in a near-duplicate group that also contains a
  val or test image, and all but one copy in groups that are train-only (the kept copy is a
  `close_up` one if there is one, then first by name).
- **Val, 2 images removed:** `wheat_septoria_blotch_Google_0212.jpg` and
  `wheat_septoria_blotch_blotch (105).jpg`, copies of test images. Neither has a tuning
  rating (the code refuses to remove a rated image).
- **Test: unchanged by this list.**
- Phase 2 sets: train 438 -> 372, val 80 -> 78.

**Collages:** `wheat_leaf_rust_Google_0358.jpg` and
`wheat_bacterial_leaf_streak_(black_chaff)_Google_0141.jpg` re-tagged `non_photo`
(`tag_source = human_decision`, `original_tag` kept). Test set 123 -> 121.

**Label conflicts:** 12 pairs listed in `report/tables/near_duplicates.md`. Rated images
involved: gold `septoria_blotch_blotch (22)`, `black_chaff)_Bing_0004`, `black_chaff (25)`,
`leaf_rust_Google_0374`, `black_chaff)_Google_0141` (already excluded) and tuning
`black_chaff)_Bing_0002`. No label changed.

**Folded-leaf calls (sheet 18, 36, 49):** accepted by Adrija as locked.

## 2026-11-14 — Phase 2 baselines retrained and re-scored after the leakage fix

**Runs:** `experiments/20261114_094320_deeplabv3plus`, `experiments/20261114_100055_segformer`
(commit `ca1a2bd`, same defaults and seed as the first runs, detached process),
re-scoring `experiments/20261114_102104_baselines_leakage_fix`
(`python -m src.rescore_after_leakage_fix`, new).

**Key metrics (test, 121 images; overall IoU with bootstrap 95% CI):**

| model | original | original, 99 non-leaked | retrained |
|---|---|---|---|
| DeepLabV3+MobileNetV3 | 0.616 (0.569-0.660) | 0.595 (0.545-0.643) | 0.586 (0.538-0.631) |
| SegFormer-B0 | 0.671 (0.626-0.710) | 0.656 (0.609-0.702) | 0.658 (0.612-0.700) |
| paired difference | +0.055 (0.037, 0.075) | +0.060 (0.040, 0.083) | +0.072 (0.052, 0.096) |

Best val IoU: DeepLabV3+ 0.5595 (epoch 17 of 27), SegFormer-B0 0.6145 (epoch 27 of 37).

**Conclusion:** the leak inflated the first results slightly (the 22 leaked test images
scored 0.710 / 0.740 with the first models, 0.636 / 0.702 after retraining). The
conclusions don't change: SegFormer-B0 is better, with a paired interval that excludes
zero. The drops are inside the CIs, and the retrained models also had 15% fewer training
images. One seed per model. Full table: `report/tables/baselines.md`.

## 2026-11-14 — Phase 4 corruption module and click rule built (not run on test)

**What:** `src/corruptions/corruptions.py` (10 corruptions x 5 levels, combined chain =
low resolution -> sensor noise -> JPEG), `src/severity/auto_click.py`,
`src/models/inference.py`, with tests. Nothing was run on test or gold images.

**Routine decisions (Claude, fast working mode), each with its reason:**
- Level parameters are hand-set placeholders (`LEVELS`): no real low-end phone photos
  exist yet to calibrate against.
- Blur sizes are scaled to the image's long side (reference 1024 px): PlantSeg images have
  very different sizes, and a fixed kernel would blur small images much more.
- Randomness is seeded from SHA-256 of (seed, corruption, level, image id): results don't
  depend on processing order or on Python's per-process hash.
- Motion-blur direction and colour-cast colour are fixed per image across levels: so a
  level only changes strength, and metric-vs-level curves are not mixed with direction.
- Exposure and colour cast are applied in linear light (gamma 2.2): a gain on gamma-encoded
  values does not behave like a real exposure change.
- Sensor noise is signal-dependent (shot + read noise): closer to a small sensor than
  plain Gaussian noise.
- Click rule: the distance transform is computed with a one-pixel border, so a component
  cut by the image edge is not treated as deep there; the click is the centre of the
  chosen output pixel mapped to photo pixels. The rule itself is the one fixed on
  2026-11-11.
- Small fix during testing: the first version drew a new blur direction at every level,
  which made level 2 weaker than level 1 on small images. Cause: direction and strength
  shared one random generator. Fixed by the per-image direction above.

## 2026-11-14 — Phase 3 step 3: refinement tuned on the 12 tuning images; method frozen (C1)

**Code:** `src/severity/refinement.py`, `severity_pipeline.py`, `tune_refinement.py`,
`evaluate_gold.py` (guarded: needs `--gold`, the locked check, the frozen checkpoint
SHA-256, and no existing gold report). Grids committed in `2de3685`, model for B in
`ef406a8`, both before the tuning run.

**Routine decisions (Claude), made before any refinement result existed:**
- Rust and necrotic groups keep Lab a* >= threshold, mildew keeps chroma <= threshold with
  L* >= 35: one number per group, as the plan's budget requires.
- Grids: rust 0..20, necrotic -5..15, mildew 8..25 (5 values each): spans from "keeps
  nearly everything that is not green" to "keeps only strongly coloured pixels".
- Thresholds tuned on input B and applied to both A and B: C on B is what the app runs.
- Method B model: the retrained SegFormer-B0 (higher test IoU, 0.658 against 0.586).
- Halo rule: yellow pixels (HSV hue 15-24) in the region are added when their connected
  component touches a kept lesion pixel: the simplest reading of the guidelines' rule.
- Ties in the grid go to the first value listed: fixed in advance to avoid a choice later.

**Run:** `experiments/20261114_102158_refinement_tuning` (commit `ef406a8`), table
`report/tables/refinement_tuning.md`.

**Key metrics (tuning MAE in points, bootstrap 95% CI):**

| method | MAE |
|---|---|
| A | 75.03 (57.40-87.60) |
| B | 77.53 (65.86-86.59) |
| C0(A) | 27.77 (14.67-44.39) |
| C0(B) | 27.24 (14.31-43.45) |
| C1(A) | 15.18 (4.88-26.25) |
| C1(B) | 15.11 (4.79-25.99) |
| C1(B), leave-one-out | 17.30 (6.83-28.18) |

Thresholds: rust 10, necrotic 15, mildew 8.

**Fallback rule:** C1 beats C0 on B by 12.13 points (9.94 leave-one-out), more than 3.64.
**Method: C1.**

**Frozen:** `severity_method` in `configs/config.yaml` (C1, the three thresholds, retrained
SegFormer-B0 with its checkpoint SHA-256), tag `phase3-method-v1`. `evaluate_gold --debug`
was run on 3 tuning images to test the code path. **No gold image has been scored.**

**Conclusion:** refinement helps a lot compared with the raw regions, but the frozen method
is still 15 points from the ratings on tuning, about four times the rating noise. Three of
12 images are off by 38 to 51 points. Necrotic 15 and mildew 8 are at the edge of their
grids; the grid was not extended. Expect a large error on gold.


## 2026-11-14 — Pre-gold round 2 (tuning images only): method not changed, phase3-method-v1 kept

Adrija's instruction: one time-boxed improvement round before gold, on tuning images only.
**Change rule (Adrija):** the frozen method changes only if leave-one-out MAE improves by
more than 3.64 points. No gold image was read in this round.

**1. Diagnosis of the 3 worst tuning images** (`python -m src.severity.diagnose_tuning`, new;
run `experiments/20261114_174059_pregold_round2_diagnosis`; figures
`report/figures/pregold_round2/diagnosis_1..3.png`: photo + click, leaf outline, model
region, refined lesions with lesion colour in red and halo in yellow).

| image | rating | method | leaf | region | colour | stage that failed |
|---|---:|---:|---|---|---|---|
| `bacterial_leaf_streak_(black_chaff)_Bing_0002` | 8.0 | 59.1 | correct leaf, 31% of image | 99% of leaf | lesion colour 14.9 + halo 44.2 | **colour (halo rule)** |
| `powdery_mildew_Google_0073` | 4.5 | 55.3 | correct leaf, 8% of image | 94% of leaf | lesion colour 55.3, no halo | **colour (chroma threshold)** |
| `septoria_blotch_blotch (125)` | 6.5 | 44.8 | clicked leaf, a few stray specks, 9% of image | 100% of leaf | lesion colour 15.4 + halo 29.4 | **colour (halo rule)** |

- The leaf stage did not fail on any of the three.
- The region stage gives no information on any of them (94 to 100% of the leaf), as on most
  tuning images; all the work is left to the colour stage.
- Mildew image: the whole leaf is pale (median chroma 6.5, median L* 92 inside the region),
  so "low chroma and not dark" cannot separate mildew from the pale leaf surface.
- **Observation for Adrija (Claude's reading of the figures, not a change to any rating):** on
  all three photos the discoloured tissue looks much larger than the rating (tan streaks over
  roughly half of the outlined leaf on `Bing_0002`; a leaf that looks dusted along its whole
  length on `Google_0073`). Part of the 38 to 51 point gap may come from what the rating
  counts as lesion, and not only from the method. The ratings were not touched.

**2. Candidates** (`configs/experiments/phase3_round2.yaml`, committed in `7ff1a25` before any
of their results existed):
- `v1`: the frozen grid (reference).
- `E`: necrotic grid extended to 20, 25, 30; mildew grid extended to 6, 4, 2.
- `F`: E, and the necrotic group may drop the halo (the stage-specific rule the diagnosis
  points to). Threshold and halo are chosen jointly, also inside each leave-one-out fold.

**3. Result** (`python -m src.severity.pregold_round2`, new, with tests; run
`experiments/20261114_174347_pregold_round2`; table `report/tables/pregold_round2.md`):

| candidate | chosen (rust / necrotic / mildew) | in-sample MAE | leave-one-out MAE (95% CI) | gain over v1 |
|---|---|---:|---|---:|
| v1 | 10 / 15 / 8 | 15.11 | 17.30 (6.83-28.18) | reference |
| E | 10 / 30 / 8 | 9.41 | 15.09 (6.93-27.17) | +2.21 |
| F | 10 / 20 no halo / 8 | 9.05 | 15.42 (7.51-27.43) | +1.88 |

**Decision: neither gain is more than 3.64, so the method is not changed.** `severity_method`
in the config is untouched, `phase3-method-v1` stays the method tag, and there is no
`phase3-method-v2`. The code state used for gold is tagged `phase3-pregold-round2`.

**What the numbers say:**
- Mildew: 8 stays the best value; 6, 4 and 2 are worse (31.5, 27.7, 21.2 against 18.9).
  The first round's edge value was not hiding a better one.
- Necrotic: the in-sample gain is large (20.8 -> 7.1 with threshold 30, or 6.2 with 20 and no
  halo), but those settings return 0 to 1% on 4 of the 5 necrotic images. With ratings of
  3.5 to 13.5 that is close to "always answer zero", which scores well only because the
  tuning ratings are all low.
- The leave-one-out gain is small because the choice is unstable: with 3 mildew images,
  leaving out `Bing_0096` moves the mildew threshold to 2 and that image goes from 55.3 to
  0.0 (rating 54.5).

**Routine decisions (Claude):**
- Three extension steps per grid, same spacing as before: "a few steps past the edge".
- Only one stage-specific rule tested (halo off for necrotic): the only one the diagnosis
  points to; nothing was tried for the region stage because no single rule is indicated.
- `refine_c1` gained a `halo` argument (default on, so the frozen method is unchanged;
  `test_real_frozen_method_matches_the_tuning_report` still passes).

**black_chaff (25) (Adrija):** `wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (25).jpg`
keeps its PlantSeg label. `annotation.gold_sensitivity_without` in the config names it, and
`evaluate_gold` now writes every headline result with and without it. Set before any gold
image was scored. The gold report also shows the resolution limit beside each result.

**Noted, not changed:** with the placeholder thresholds (`high_max: 1.00`) the level "high"
needs 100% severity, so in practice there are three levels (none below 5%, low below 20%,
medium above) and the decision "consult_expert" is never reached. Placeholder, for Adrija.

## 2026-11-14 — Phase 3 step 4: the single gold evaluation (frozen method phase3-method-v1)

**Run once**, on Adrija's go-ahead given in advance ("run the single gold evaluation without
waiting for me"): `python -m src.severity.evaluate_gold --gold`, commit `07f085e` (tag
`phase3-pregold-round2`), run `experiments/20261114_174642_gold_evaluation`, table
`report/tables/gold_evaluation.md`. The script now refuses to run again (the table exists).

**Key metrics (37 gold images, severity MAE in points, bootstrap 95% CI; resolution limit 3.64):**

| method | pooled MAE | mean signed error | same level | same decision |
|---|---|---:|---:|---:|
| A (PlantSeg region) | 65.65 (55.80-74.38) | +65.65 | 22% | 22% |
| B (model region) | 59.02 (48.99-67.39) | +58.85 | 19% | 19% |
| C(A) | 14.41 (10.05-19.27) | +1.28 | 24% | 24% |
| C(B), the frozen method | 14.35 (9.97-19.23) | +1.22 | 24% | 24% |

C(B) by rating band: low (< 10%, n = 25) 11.98 (6.48-18.98); medium (10 to < 20%, n = 6)
11.51 (6.40-17.15); high (>= 20%, n = 6) 27.05 (22.69-31.25).
C(B) by disease: bacterial leaf streak 7.11, leaf rust 13.77, powdery mildew 11.69, septoria
blotch 18.33, stripe rust 19.21 (n = 5 to 9 each; CIs in the table).

**Without black_chaff (25)** (36 images): C(B) 14.56 (10.03-19.97), same level 22%. The
difference from the main result (0.21 points) is far below the resolution limit.

**Conclusion:**
- The frozen method is about 14 points from the ratings, four times the rating noise, as the
  tuning result predicted (15.1 in-sample, 17.3 leave-one-out). Not a usable absolute
  severity.
- Refinement is what matters (59 -> 14 points); A and B inputs give the same result after it
  (14.41 against 14.35, not distinguishable).
- The mean signed error is near zero (+1.2) while the MAE is 14: the method errs in both
  directions. Of 25 low-band images, 13 are scored "none"; all 6 high-band images are far
  off (27 points).
- Level and decision agreement is 24% with the PLACEHOLDER thresholds. With three levels in
  practice, that is below what always answering "low" would give (23 of 37 = 62%, from the
  confusion counts). The absolute severity level from this method must not be presented as
  advice.
- Gold is single-rater and the leaf check was AI-judged; see `report/limitations.md`.
- No re-tuning follows. Phase 4 measures consistency under corruption, which does not depend
  on the absolute error.

## 2026-11-14 — Phase 4: corruption benchmark run on test (121) and gold cross-check (37)

Adrija's instruction: continue directly into Phase 4 on test after the gold evaluation.

**Code:** `src/corruptions/benchmark.py` (new, with `tests/test_benchmark.py`), config
`configs/experiments/phase4_benchmark.yaml`. One command:
`python -m src.corruptions.benchmark`. Run `experiments/20261114_175018_phase4_benchmark`
(commit `4ef1704`, about 40 minutes on the RTX 3050). Outputs: `report/tables/robustness.md`,
`report/figures/robustness/` (metric-vs-level figures and the flip-rate heatmap, for test
and `_gold`). 2 models x 10 corruptions x 5 levels; corrupted images made on the fly.

**Routine decisions (Claude), each with its reason:**
- "Severity MAE" on test = mean |severity(corrupted) - severity(clean)| for the same model
  ("severity shift"): test images have no ratings, and the research question is the shift.
  On gold the MAE against the rating is reported as well.
- Severity under corruption is the frozen Phase 3 method run end to end on the corrupted
  pixels (region, SAM 2 leaf, colour refinement): that is what a phone would do.
- mIoU is computed in the model's padded 512 px space: the clean values then equal the
  Phase 2 test IoU exactly (0.658 and 0.586, checked).
- An image with no estimate (empty leaf) counts as a flip: the app could give no advice.
  It did not happen (0 cases).
- Leaf IoU against the clean leaf is recorded too: it separates leaf-mask changes from
  region and colour changes.
- Per-image records are written as they are produced, with `--resume`: a long run must
  survive an interruption.
- `--debug` uses 3 test and 3 tuning images, never gold.
- Figures: both models in one panel per corruption, with a bootstrap band; one colour-blind
  safe pair of colours.

**Key metrics, test set, SegFormer-B0** (flip rate with bootstrap 95% CI; PLACEHOLDER
levels, thresholds and mapping):

| corruption | mIoU, level 5 (clean 0.658) | severity shift, level 3 / 5 | flip rate, level 3 | flip rate, level 5 |
|---|---:|---:|---|---|
| sensor noise | 0.514 | 10.3 / 14.2 | 0.46 (0.38-0.55) | 0.53 (0.44-0.62) |
| colour cast | 0.647 | 11.7 / 16.8 | 0.37 (0.29-0.46) | 0.48 (0.39-0.57) |
| over-exposure | 0.562 | 6.6 / 12.9 | 0.31 (0.23-0.39) | 0.50 (0.42-0.60) |
| under-exposure | 0.604 | 7.8 / 11.7 | 0.28 (0.21-0.36) | 0.41 (0.32-0.50) |
| Gaussian blur | 0.541 | 5.7 / 7.5 | 0.19 (0.12-0.26) | 0.26 (0.19-0.35) |
| defocus blur | 0.554 | 5.2 / 6.9 | 0.17 (0.11-0.24) | 0.25 (0.17-0.33) |
| motion blur | 0.575 | 3.9 / 5.1 | 0.16 (0.10-0.23) | 0.20 (0.13-0.27) |
| combined chain | 0.462 | 3.7 / 6.9 | 0.14 (0.08-0.21) | 0.21 (0.15-0.29) |
| JPEG | 0.595 | 2.1 / 6.8 | 0.08 (0.03-0.13) | 0.16 (0.10-0.22) |
| low resolution | 0.576 | 1.7 / 4.0 | 0.07 (0.03-0.12) | 0.18 (0.12-0.26) |

**Conclusions:**
- **Segmentation accuracy does not show the decision instability.** Colour cast at level 5
  leaves mIoU almost unchanged (0.658 -> 0.647) while 48% of decisions flip. Sensor noise at
  level 1 costs 0.02 mIoU and flips 34%. This is the effect the project set out to measure.
- **The corruptions that change colour or brightness hurt most** (noise, colour cast,
  exposure), the ones that remove detail hurt least (JPEG, low resolution). The severity
  method is a colour threshold, so this is where it is fragile.
- **Direction:** noise pushes severity up (92 of 121 images at level 5, mean +7.6 points:
  mostly "none" -> "low"); colour cast, over-exposure and blur push it down (mean -7.0,
  -4.7, -4.8 points).
- **The two models flip equally often** (flip rates within a few points everywhere)
  although DeepLabV3+ loses much more mIoU under noise (0.586 -> 0.290 against 0.658 ->
  0.514). The region covers most of the leaf, so the colour rule and the leaf decide the
  severity. A better region model would not fix this.
- **The combined chain (low resolution -> noise -> JPEG) flips less than noise alone**
  (0.21 against 0.53 at level 5) although its mIoU and its leaf IoU (0.46) are the worst.
  Probable reason, not tested: the JPEG step smooths the noise that shifts pixel colours
  across the threshold. Not what the plan expected of the "realistic" chain; noted for
  Adrija.
- **The leaf moves too:** leaf IoU with the clean leaf falls to 0.71-0.76 for blur and noise
  at level 5 and to 0.46 for the combined chain on test.
- **Gold cross-check (real clicks, 37 images):** same picture (sensor noise 0.46, colour
  cast 0.54, over-exposure 0.51 at level 5, SegFormer-B0), wider CIs. The leaf is more
  stable with real clicks (0.83 to 0.96 at level 5, 0.53 combined). MAE against the rating
  stays at 11 to 15 points at every level: the clean error is so large that corruption does
  not make it visibly worse, so only the shift measures the damage.
- **Threshold effect:** on clean test images the method's median severity is 4.2%, next to
  the 5% placeholder threshold (62 none, 21 low, 38 medium), and 19% of images are within 3
  points of a threshold. The flip rate depends on where the thresholds sit; the severity
  shift in points does not.

**Caveats:** corruption levels are hand-set placeholders, so comparisons between
corruptions at "the same level" are not fair comparisons of their real-world severity; the
severity method is about 14 points from gold; one seed per model.

## 2026-11-14 — Adrija's decisions after Phase 4: rating definition, corrected level mapping, Phase 5 redirected

**Rating definition (Adrija):** when rating, she **included discoloured tissue**. Recorded in
`docs/annotation_guidelines.md`. So the gap on the three diagnosed tuning photos is not
explained by a narrower rating definition. No exploratory gold analysis without the halo was
run (it was only to be run for the other answer). No rating changed.

**Level mapping (Adrija), still PLACEHOLDER:** none = exactly 0%, low = above 0 and below 5%,
medium = 5% to below 20%, high = 20% or more. Decisions: none -> no_action, low -> monitor,
medium -> treat, high -> treat_urgently. `consult_expert` now comes only from Phase 6
abstention. Changed in `configs/config.yaml` and `recheck_report.severity_level` (tests
updated). The old mapping was none < 5%, low < 20%, medium < 100%, high = 100%.

**Re-reported, nothing re-scored:**
- Gold (`python -m src.severity.rereport_gold_levels`, new; `report/tables/gold_levels_v2.md`):
  re-binned from the saved per-image severities of the single gold run. C(B): same level and
  same decision **22%** (8 of 37); old mapping 24%. MAE unchanged (14.35).
  `report/tables/gold_evaluation.md` is left as written by the gold run.
- Phase 4 (`python -m src.corruptions.benchmark --report-only <run>`, new option;
  `report/tables/robustness.md`; the old table is kept as
  `report/tables/robustness_old_levels.md` and the old numbers are in the Phase 4 entry
  above). Flip rates rise with the new mapping, because "none" is now a single point (0%)
  and the 5% and 20% boundaries both separate decisions:

| SegFormer-B0, test | old flip, level 3 / 5 | new flip, level 3 / 5 |
|---|---|---|
| sensor noise | 0.46 / 0.53 | 0.55 / 0.58 |
| colour cast | 0.37 / 0.48 | 0.54 / 0.67 |
| over-exposure | 0.31 / 0.50 | 0.40 / 0.60 |
| under-exposure | 0.28 / 0.41 | 0.40 / 0.55 |
| Gaussian blur | 0.19 / 0.26 | 0.30 / 0.45 |
| defocus blur | 0.17 / 0.25 | 0.26 / 0.40 |
| motion blur | 0.16 / 0.20 | 0.26 / 0.37 |
| combined chain | 0.14 / 0.21 | 0.26 / 0.36 |
| JPEG | 0.08 / 0.16 | 0.17 / 0.26 |
| low resolution | 0.07 / 0.18 | 0.17 / 0.30 |

- **Single-threshold flip rates** (new, `phase4.flip_thresholds` in the config): the share of
  images whose estimate crosses one threshold between clean and corrupted. Mean over the 50
  corruption x level cells, SegFormer-B0, test: 3%: 0.18, 5%: 0.16, 10%: 0.13, 20%: 0.10
  (DeepLabV3+: 0.18, 0.16, 0.13, 0.11). Mean flip rate with the full mapping: 0.32.
  **Mean severity shift: 5.71 points** (DeepLabV3+ 5.88); this stays the primary,
  threshold-free metric.

**Routine decisions (Claude):**
- Gold levels re-binned from the saved run, not re-run: gold is scored once.
- `robustness.md` regenerated from the saved records with `--report-only`: no image was
  processed again, so the two tables differ only in the mapping.

**Phase 5 redirected (Adrija):** make the colour stage robust (colour constancy, exposure
normalisation, light denoising before the colour rule), selected with test flip rate and
severity shift plus a tuning leave-one-out guard of 3.64 points; gold not used; one
corruption-augmented SegFormer as a short baseline. Plan with variants and the selection
rule: `configs/experiments/phase5_colour_stage.yaml`, committed in `776e6e1` before any
Phase 5 result.

## 2026-11-16 — Phase 5: colour-stage variants on test and val; `denoise+shades_of_gray+exposure` selected

**Run:** `experiments/20261115_104906_phase5_colour_stage` (config
`configs/experiments/phase5_colour_stage.yaml`). Per-image records were finished on
2026-11-15 (121 test, 78 val images, 61 conditions each, both region models); the run stopped
before the summary step and was resumed on 2026-11-16 with `--resume` (no image re-processed).
Gold not used. Table: `report/tables/phase5_colour_stage.md`; figures: `report/figures/phase5/`.

**Corruption-augmented baseline:** `experiments/20261114_184149_segformer_corruption_aug`
(`--corruption-aug 0.5`, early stop at epoch 52, best val IoU 0.615 at epoch 42). Added to the
Phase 5 YAML on 2026-11-15 after training; it takes no part in the selection.

**Selection (rule written in the YAML before the results):** all 12 variants are admissible
(tuning leave-one-out MAE within 3.64 points of `none`, 17.30). Lowest mean test severity
shift: `denoise+shades_of_gray+exposure`, thresholds rust 5 / necrotic 15 / mildew 8. It
replaces `none` (shift lower, flip rate not higher).

**Key metrics, SegFormer-B0 regions, mean over the 50 corruption x level cells** (flip rates
with the PLACEHOLDER levels and mapping; corruption levels are placeholders):

| colour stage | test shift, points | test flip | val shift | val flip | tuning leave-one-out MAE | clean test estimates = 0 |
|---|---:|---:|---:|---:|---:|---:|
| `none` | 5.71 | 0.32 | 6.22 | 0.33 | 17.30 | 27% |
| `denoise+shades_of_gray+exposure` | 4.27 | 0.20 | 3.58 | 0.21 | 19.23 | 28% |

Corruption-augmented region model, test: shift 5.69 / flip 0.32 with `none`, 4.29 / 0.21 with
the selected stage (clean mIoU 0.665 against 0.658; mean mIoU over the 50 cells 0.640
against 0.614).

**Conclusions:**
- The gain comes from colour cast (shift at level 5: 16.8 -> 4.9), under-exposure
  (11.7 -> 3.1) and sensor noise (14.2 -> 9.0). Blur is unchanged; over-exposure is unchanged
  (12.9 -> 12.8: clipped pixels cannot be recovered by a gain).
- **It is worse on three corruptions at the high levels:** combined chain (6.9 -> 8.8 at
  level 5, flip 0.36 -> 0.45), JPEG (flip 0.26 -> 0.37 at level 5) and low resolution
  (4.0 -> 5.7). The mean hides this.
- **The selected variant has the worst tuning leave-one-out MAE of the 12** (19.23, 1.93
  points worse than `none`; inside the 3.64 guard). Stability was bought with a slightly
  worse fit to the 12 tuning ratings. Its accuracy against gold is unknown: gold was scored
  once with `none` and is not re-scored.
- The share of clean estimates equal to 0 is the same (27% and 28%), so the stability is not
  from answering zero more often.
- The validation split, which took no part in the selection, ranks the same variant first.
- **Corruption-augmented training of the region model does not change severity stability**
  (5.69 against 5.71) although it raises mIoU under corruption. Same finding as Phase 4: the
  colour rule and the leaf decide the severity, not the region.
- **Combined-chain ablation:** noise then JPEG has a far smaller shift than noise alone (6.0
  against 14.2 at level 5), low resolution then noise does not (15.6). This supports the
  Phase 4 guess that the JPEG step smooths the noise.

**Routine decisions (Claude):**
- Resumed from the saved records, not re-run: the records were complete and resuming cannot
  change them.
- The selected variant and thresholds were copied into `configs/experiments/phase6_abstention.yaml`
  and committed (`0285538`) before the Phase 6 run, as that file requires.

## 2026-11-17 — Phase 6: quality gate, uncertainty and abstention (val fits, test evaluates)

**Run:** `experiments/20261116_120119_phase6_abstention` (config
`configs/experiments/phase6_abstention.yaml`; the Phase 5 colour stage was copied in and committed
before the run, `0285538`). Started 2026-11-16 with 8 workers; stopped by Claude Code for low system
memory after val (78/78) and 14/121 test images; resumed 2026-11-17 with `--resume --workers 4` (no
image re-processed). Report code at commit `8d18a52`. Table `report/tables/abstention.md`; figures
`report/figures/phase6/`. Gold not used.

**Added before the results (Adrija's request, `8d18a52`):** the gate's catch rate among unreliable
estimates (shift > 3.64) per corruption and level, and the full policy's catch rate.

**Key metrics, corrupted test photos (6050 estimates, 121 images); error = shift from the clean
estimate; flip rate with the PLACEHOLDER mapping:**
- No abstention: shift 4.27 points, flip rate 0.20.
- Policy score chosen on val: tiny classifier on gate features + scores (val shift AURC 1.33; test
  2.45). At 80% coverage: shift **2.86 (1.91-3.88), -33%**; flip rate 0.20 (0.16-0.24), -2%. At 90%:
  shift 3.34, -22%; flip 0.20, -4%.
- Best single scores on test: photometric TTA spread (AUROC 0.74, shift AURC 2.34) and mirror TTA
  (0.70, 2.54). Softmax entropy is near chance (AUROC 0.54).
- Quality gate: retakes 55% of corrupted test photos (mean shift 5.00 when it fails, 3.40 when it
  passes) and **19% of clean test photos** (15% on val).
- Gate catch rate among unreliable estimates: over-exposure 90%, Gaussian blur 87%, sensor noise 85%,
  under-exposure 81%, defocus 79%, low resolution 62%, motion blur 50%, colour cast 34%, **JPEG 21%,
  combined chain 14%** (8% at level 5, where 51% of estimates are unreliable).
- Gate test set: of 23 `skip` images, 61% fail a photo or framing check; the non-disputed `wide` set is
  empty (all 21 `wide` are disputed; 29% of them fail).

**Conclusions:**
- **Abstention lowers the severity shift but not the decision flip rate.** No score cuts the flip
  rate by more than a few points at 80-90% coverage; the policy score's flip rate is above the
  no-abstention rate between about 45% and 75% coverage. The policy score was chosen on shift AURC
  (the primary metric), so flips were not optimised.
- **The gate does not cover Phase 5's weak spots.** JPEG and the combined chain are sent back at about
  the clean-photo rate (17-24% and 11-21%): the checks see blur, noise and exposure, not compression.
  The combined chain is sent back *less* often than clean photos (probable reason, not tested:
  downscaling and JPEG smooth the noise and clipped pixels the checks look for). Low resolution is
  caught 62%; colour cast 34% (the cast feature is not one of the checks).
- **Result that contradicts the plan (checkpoint c):** the gate refuses about 52% of corrupted val
  photos, so the 80% and 90% target coverages cannot be reached. The uncertainty threshold becomes the
  maximum score and **"consult an expert" is never used** (0% at both targets): the full policy is the
  gate alone, at 45% coverage. The thresholding rule is frozen; not changed.
- **The gate's clean false-retake rate is 15-19%, not "a few percent"** as the YAML comment expected.
  The 2.5% is per check and side; with six checks (brightness two-sided) and the fixed 224 px minimum
  side (5% of clean photos are smaller), the rates add up. Not changed (frozen).
- The full classifier's val AURC (1.33) is far better than its test AURC (2.45): it was fitted and
  chosen on the same val estimates.

**Routine decisions (Claude):** resumed with 4 workers after the memory stop; nothing re-scored.

## 2026-11-17 — Phase 6 v2 (POST HOC): revised gate and abstention policy, one test evaluation

**Decision (Adrija, 2026-11-17):** v1 stays the pre-registered result (tag `phase6-v1`, `e8b6c0b`),
reported unchanged. One post-hoc v2 round, fitted on validation only, evaluated once on test.
Rules and code committed `50a346b` and tagged `phase6-v2-prereg` before the test evaluation:
`configs/experiments/phase6_v2.yaml`, `src/uncertainty/phase6_v2.py`.

**Changes:** (1) one overall 5% false-retake target on clean val photos, split evenly over the check
sides, with the minimum side fitted inside the budget instead of the fixed 224 px; (2) JPEG
blockiness check (step across 8 px block boundaries / step elsewhere, full resolution); (3) coverage
measured among gate-passed photos; (4) classifiers' C and the policy score chosen by grouped 5-fold CV
inside val (out-of-fold scores, also used for the thresholds); (5) flip rates at single thresholds.

**Run:** `experiments/20261117_173140_phase6_v2` (reuses the v1 records; only blockiness recomputed).
Table `report/tables/abstention_v2.md`; figures `report/figures/phase6_v2/`.

**Key metrics, test (flip rates with the PLACEHOLDER mapping):**
- Gate: clean photos sent back **7% on test** (0% on val, where it was fitted; v1 15% / 19%).
  Corrupted photos sent back 44% (v1 55%).
- **The 5% budget could not be split finely on 78 val photos:** any tail above 0 sends back the most
  extreme photo on each of the 8 check sides, i.e. 9% of clean val photos. So the fitted tail is 0 and
  every range is the min-max of the clean val photos (minimum side 169 px). Test false retake (7%) is
  above the 5% target.
- Min side: 4 of 78 val and 6 of 121 test clean photos are below 224 px; the fitted bound is 169 px.
- Policy score (CV): tiny classifier on gate features + scores (C = 0.1; out-of-fold val AURC 1.07).
- Among gate-passed corrupted test photos (3400 of 6050): shift 3.31 -> **1.97 at 80% coverage (-41%)**,
  2.30 at 90% (-31%); flip rate 0.17 -> 0.17 (+4%) and 0.16 (-2%).
- Full policy, 80% target: corrupted photos 44% retake / **12% consult** / 44% answered (answered shift
  1.91 against 4.27 without the policy, flip 0.17 against 0.20); clean photos 7% retake / 20% consult /
  73% answered. 90% target: consult 6% corrupted, 9% clean.
- Gate catch rate among unreliable estimates, v1 -> v2: JPEG 21% -> 43% (84% at level 5), combined
  chain 14% -> 31% (81% at level 5; 4-11% at levels 1-4), low resolution 62% -> 46%, colour cast
  34% -> 15%, over-exposure 90% -> 60%. **Policy catch rate (80%)**: JPEG 76%, combined 75%, low
  resolution 60%, colour cast 78%, sensor noise 94%.
- Flips by threshold (v2 policy, gate-passed, 80% coverage): crosses 0% 0.09, 3% 0.07, 5% 0.08,
  10% 0.04, 20% 0.03. v1 policy, all corrupted, 80%: 0.10, 0.09, 0.10, 0.06, 0.04. Clean test
  estimates: 28% exactly 0, 22% in (0, 5%), 16% within 3 points of 5%, median 4.9%.

**Conclusions:**
- v2 makes "consult an expert" fire and lowers the clean-photo retake rate (19% -> 7%), at the cost of
  catching fewer exposure and colour-cast problems at the gate; the uncertainty step catches most of
  those instead.
- JPEG and the combined chain are now caught at level 5 by the gate, but not at levels 1-4.
- **Abstention still does not reduce flips.** Flips cross the 0% boundary as often as the 5% one:
  half the clean estimates are below 5% (28% are exactly 0). A flip needs only a small shift near a
  boundary, which every score (built to predict large shifts) ranks as reliable; even ordering by the
  true shift (oracle) leaves a 0.10 flip rate at 80% coverage. So the flip rate is mostly a property
  of where the placeholder boundaries sit relative to the estimates, not something abstention on
  shift can remove. **This only partly supports "estimates cluster near 5%"**: the 0% boundary
  (none = exactly 0) matters as much.
- 5% overall target on 78 photos is too fine; the fitted gate is just the observed clean range.

**Routine decisions (Claude):**
- Even split of the budget implemented as one common tail percentile for every check side, the
  largest (0.05-point grid) meeting the target.
- Thresholds from out-of-fold scores (the final classifier is refitted on all val; out-of-fold scores
  have the spread it will have on new photos).
- Framing check kept as in v1 (not part of the requested changes).

## 2026-11-17 — Phase 7 blocked: PlantDoc has no wheat

Checked the official PlantDoc repositories (github.com/pratikkayal/PlantDoc-Dataset and
PlantDoc-Object-Detection-Dataset, read 2026-11-17). The classification set has 28 class folders
(train; 27 in test) covering apple, bell pepper, blueberry, cherry, corn, grape, peach, potato,
raspberry, soybean, squash, strawberry and tomato. **None is wheat.** The object-detection set is a
CSV (`filename,width,height,class,xmin,ymin,xmax,ymax`) with the same naming; only part of its label
file was read, and no wheat label was seen. Licence: CC BY 4.0. PlantDoc is not downloaded
(`data/raw/plantdoc` does not exist) and `data/own_photos/` is empty.

So the Phase 7 plan (disease- and box-level checks of the wheat model on PlantDoc) cannot be run.
Nothing was changed; the choice of a replacement held-out wheat field set is Adrija's (checkpoint c).

## 2026-11-18 — Phase 7 set-up: Mendeley Wheat Leaf Dataset in, NWRD not used, photos capped at 2048 px

**Datasets (Adrija, 2026-11-17/18; details and licences in `report/dataset_versions.md`):**
- Mendeley Wheat Leaf Dataset (CC BY 4.0, DOI 10.17632/wgd66f8n6h.1): downloaded, SHA-256 matches the
  Mendeley record, 407 photos (102 healthy, 97 septoria, 208 stripe rust); one byte-identical copy is
  counted once, so 406 are used. Evaluation only.
- NWRD: **attempted, not used**: the download site (dll.seecs.nust.edu.pk) refused connections and no
  data licence is stated (the paper is CC BY 4.0, the code MIT). The NWRD code path stays but is not run.
- IEEE DataPort wheat rust set skipped (Adrija).

**Run stopped and restarted:** the first full run (`experiments/20261117_180903_phase7_mendeley`, full
resolution, about 36 s per photo) was stopped by Claude Code for low system memory after 63 of 406
healthy photos. Its records are not used and were not summarised.

**Change (Adrija, 2026-11-18), decided for memory and speed, not results:** every Mendeley photo is
downscaled (area interpolation) to a long side of at most 2048 px before the pipeline
(`mendeley.max_long_side` in `configs/experiments/phase7_external.yaml`). The app will downscale photos
anyway. The run restarts from the start, including the 63 photos already done.

**Routine decisions (Claude):**
- Healthy leaves have no disease to choose the colour rule, so all three rules are run and reported.
- The Phase 6 v2 classifier is refitted deterministically from the same validation records, and the
  refit is checked against the v2 run's chosen C before use.

## 2026-11-18 — Phase 7: final pipeline on the Mendeley Wheat Leaf Dataset (406 photos)

**Run:** `experiments/20261118_152635_phase7_mendeley` (commit `2fa9a97`, photos capped at 2048 px).
Table `report/tables/phase7_mendeley.md`; figures `report/figures/phase7/`. Image-level labels only, so
no severity error can be measured. PLACEHOLDER levels and decisions; the policy is Phase 6 v2 (post hoc).

**Key metrics:**
- Healthy (101): estimated at exactly 0% with the rust rule 68% (95% CI 59-77%), at most 1% 88%;
  necrotic rule 93% / 100%; mildew rule 45% / 73% (p90 7.2%, max 79.9%; 8 photos "high").
- Stripe rust (208, rust rule): detected (> 0%) 73% (66-78%); median 2.8% (IQR 0.0-7.7), p90 13.5%.
- **Septoria (97, necrotic rule): detected 6% (2-11%); 94% are exactly 0%**, although the region model
  covers a median 68% of the leaf.
- Gate retakes: healthy 25% (blur 12%, noise 11%, exposure 7%), stripe rust 12%, septoria 4%.
  Consult an expert (80% target): 0-7%.
- Leaf share of the photo: median 0.10-0.13.

**Diagnostic (not tuning), run after the result:** the same septoria photos with the Phase 3 colour stage
(`none`) are detected 84% (median 37.9%). The saved Phase 5 records show the same on PlantSeg: share of clean
septoria estimates at exactly 0%, `none` -> selected, test 29% -> 50%, val 19% -> 62%; bacterial leaf streak
test 47% -> 65%. The overall zero share checked in Phase 5 (27% -> 28%) hid it, because powdery mildew moved the
other way (21% -> 7%).

**Conclusions:**
- **Result that contradicts the plan (checkpoint c): the Phase 5 colour stage suppresses the necrotic
  (septoria, bacterial leaf streak) rule.** Part of Phase 5's stability gain on those diseases comes from
  answering 0%. This was visible in the Phase 5 records but not in the per-variant summary. The selection rule
  was followed as written; it had no per-disease guard. Nothing is changed here.
- Stripe rust works on the new source; healthy leaves mostly get 0-1% with the rust and necrotic rules, but the
  mildew rule gives false severity on healthy leaves (55% above 0%).
- The gate sends back many healthy field photos (25%), mostly blurred or noisy backgrounds.

**Routine decisions (Claude):** the diagnostic was run once, on the septoria photos only, to tell whether the
Phase 5 stage or the method itself causes the misses; it is reported, not used to choose anything.

## 2026-11-18 — Phase 5 v2 (POST HOC) rules: per-group colour stage with guards (before any v2 result)

**Decision (Adrija, 2026-11-18):** fix Phase 5 as a post-hoc v2, clearly labelled; v1 and the Phase 7 finding
stay in the drafts unchanged. One preprocessing variant per refinement group (rust, necrotic, mildew),
including `none`, chosen with validation, tuning and a healthy guard set only. Rules in
`configs/experiments/phase5_v2.yaml`, code `src/severity/phase5_v2.py`; committed and tagged `phase5-v2-prereg`
before the run.

**Guards (Adrija):** G1 per-group tuning leave-one-out MAE at most 3.64 worse than `none`; G2 per disease, the
clean val zero rate not above `none`'s; G3 per group, healthy median false severity and share above 5% not above
`none`'s. Among passing variants: lowest val mean shift, then val flip; replaces `none` only if the shift is lower
and the flip rate not higher (same replacement rule as v1, applied per group).

**Why not PlantSeg's own healthy images (asked by Adrija):** PlantSeg has none. It is a disease-segmentation set;
no v7 label contains "healthy", and all 1,166 wheat images have a non-empty lesion mask. So G3 uses another set.

**Healthy guard set (Adrija):** Bangladesh wheat field set (Mendeley 5gc7hwydwg v1, CC BY 4.0), the 250 ORIGINAL
healthy leaf photos only (`Wheat Disease/Original Dataset/HealthyLeaf`; augmented and split copies not used).
SHA-256 of the archive matches the Mendeley record. Mendeley Wheat Leaf (Ethiopia) is excluded because the
problem was found there; the JIC set (Zenodo 7573133, CC BY 4.0) is reserved as an untouched external test,
not downloaded until Phase 5 v2 and the re-fitted Phase 6 policy are tagged. Class mapping for JIC fixed now
(`report/dataset_versions.md`).

**Routine decisions (Claude):**
- Per-group tuning LOO = the Phase 5 v1 leave-one-out predictions restricted to that group's tuning images
  (thresholds are chosen per group, so a group's LOO depends only on its own images). Tuning images per group:
  rust 4, necrotic 5, mildew 3, so G1 is a weak guard.
- Healthy photos capped at 2048 px and the automatic click, as in Phase 7.
- Val and test severities of every variant are read from the saved Phase 5 v1 records (identical to running the
  per-group stage, since each record holds every variant with its own thresholds).
- `--debug` uses val in place of test, so test is not looked at before the single evaluation.
- Phase 6 and Phase 7 code now accept a per-group colour stage (`colour_stage.per_group`); old configs unchanged.

## 2026-11-18 — Phase 5 v2 (POST HOC) result: every group selects `none`

Run `experiments/20261118_164312_phase5_v2`, table `report/tables/phase5_v2.md`, rules tagged `phase5-v2-prereg`.
- In every group, only `none` passes all three guards. Rust: the variants fail G2 (stripe rust val zero rate above
  16%), G3 (healthy share above 5% higher than 8%) or G1 (gray-world variants). Necrotic: every variant fails G2
  (septoria or BLS zero rate higher) or G3. Mildew: G2, G1, or G3 (gray-world variants give 44-47% of healthy
  leaves above 5%).
- So v2 = the Phase 3 colour stage for all diseases. Test (single evaluation), v2 against v1, pooled: clean zero
  rate 27% vs 28%, mean shift 5.71 vs 4.27 points, flip rate 0.32 vs 0.20. Septoria: zero rate 29% vs 50%,
  shift 9.62 vs 4.98. BLS: 47% vs 65%.
- Healthy guard set (Bangladesh, n = 250), share above 5%, `none` vs v1: rust 8% vs 10%, necrotic 6% vs 2%,
  mildew 4% vs 15%.
- Note: G2 compares zero rates on small val groups (leaf rust 5, BLS 11, septoria 16 images), so one image
  decides it. Ties pass, so the guards favour `none`. This is a property of the frozen rules, not a change to them.
- Conclusion: the guards remove v1's robustness gain together with its detection loss. No v2 variant keeps one
  without the other. Phase 6 re-score, Mendeley v2 and JIC are on hold for Adrija's decision (checkpoint c).

## 2026-11-18 — Final pipeline: Phase 6 v2 re-fitted on Phase 5 v2; Mendeley re-run; frozen as final-v1

Adrija accepted Phase 5 v2 (2026-11-18) and asked for the Phase 6 v2 policy on it, a Mendeley re-run (labelled
not independent), a freeze, then the single JIC run.
- Phase 6 re-score on the v2 stage: `experiments/20261118_174507_phase6_abstention` (config
  `phase6_on_phase5_v2.yaml`, gate-set features reused). Frozen v2 rules re-fitted:
  `experiments/20261118_182200_phase6_v2`, `report/tables/abstention_final.md` (blockiness reused, photos only).
- The frozen CV rule now picks the photometric TTA spread (val out-of-fold AURC 3.01 vs classifier 3.28). Phase 7
  code extended to use a raw score as policy (routine; no rule change).
- Test, gate-passed: shift 4.36 -> 3.29 at 80% coverage (-25%), flip 0.27 -> 0.27. Full policy 80%: corrupted
  44% retake / 11% consult / 45% answered; clean 7% / 22% / 70%. Colour cast is the gap: gate catch 12%, policy 41%.
- Mendeley final (NOT INDEPENDENT), `experiments/20261118_182347_phase7_mendeley`: detected septoria 84% (v1
  stage 6%), stripe rust 96% (73%); healthy > 0% rust 14% (32%), necrotic 9% (7%), mildew 36% (55%).
- Final pipeline = SegFormer-B0 region, automatic click, SAM 2 leaf, no colour preprocessing (thresholds rust 10,
  necrotic 15, mildew 8), Phase 6 v2 gate and photometric-spread policy from the run above. Tagged `final-v1`
  before JIC is downloaded.
- Drafts: v1 stability gain (flip 0.32 -> 0.20) kept only as v1 history; trade-off finding added; mildew
  false-alarm limitation added.

## 2026-11-21 — JIC download and layout (before the single JIC run)

- Downloaded after `final-v1` (first try timed out at 1 h, resumed). MD5 matches Zenodo.
- Flat layout, class in the file name (Septoria 349, YellowRust 239, Mildew 161, BrownRust 128, Healthy 122).
  Routine: extracted into one folder per file-name prefix so the class lookup (folder keywords) works; mapping
  unchanged. Debug run (5 photos, outputs in the experiment folder only) not looked at for results.

## 2026-11-21 — Phase 7 JIC: single independent evaluation of final-v1

Run `experiments/20261121_225538_phase7_mendeley` (config `phase7_jic.yaml`), `report/tables/phase7_jic.md`.
- Detected (> 0%): stripe rust 82%, leaf rust 88%, septoria 58%, powdery mildew 80%.
- Healthy (n = 122) above 0%: rust rule 29%, necrotic 20%, mildew 63%; median 0% for all; at "high": 10 / 7 / 8.
- Gate retake 3-6%; consult an expert at 80%: 6-19%. Leaf share median 4-8% (crowded canopies).
- Conclusion: the final pipeline detects rust and mildew on an independent source; septoria is weak and healthy
  false alarms (mildew rule) remain. No further changes: this was the single evaluation.

## 2026-11-21 — Packaging: demo, export, README, release check (Adrija: resume project, fast mode)

- Demo (`demo/app.py`, `src/demo/`): Gradio, frozen final-v1 pipeline, user tap instead of the automatic click.
  Policy values exported once to `demo/final_policy.json`. Check: with the JIC run's own clicks the demo reproduces
  the frozen JIC severities and actions (3 photos, differences < 0.001 points, CPU vs GPU). About 2 s per photo on CPU.
  `phase7.score_photo` got two optional arguments (click, return_masks); defaults unchanged.
- Examples: 3 JIC photos (CC BY 4.0), picked from the JIC run as clear single-leaf photos with an "answer" result.
  No mildew example: the JIC mildew photos are pot shots with labels.
- HF Space bundle: `python -m src.demo.build_space` (dist/ gitignored); standalone run checked locally.
- Export (`src/export.py`, `report/tables/export.md`, run `experiments/20261121_233718_export`): ONNX FP32 15.0 MB
  158 ms; INT8 dynamic (MatMul/Gemm only, because dynamic Conv becomes ConvInteger, which ORT CPU lacks) 7.8 MB, IoU
  -0.002; INT8 static QDQ (100 training images for calibration) 4.5 MB, IoU +0.003, region agreement 0.91. TFLite
  not done (needs a TensorFlow toolchain). onnx 1.17.0, onnxruntime 1.20.1 and onnxscript 0.1.0 installed for the export.
- README rewritten from the drafts. Robustness numbers taken from `report/tables/robustness.md`: the Phase 4
  draft's level-5 flip-rate table is stale (older levels) and should not be quoted.
- Release check (kept outside the repository); ATTRIBUTION.md extended (Mendeley and JIC overlays, three
  PlantSeg figure sets). Nothing made public.

## 2026-11-22/23 — Public release (Adrija)

- Public repository `adrijas7274/wheat-disease-severity`: a single fresh commit made from this repository's files,
  minus private planning files and the release checklist. Author: Adrija Sarkar (GitHub
  no-reply address), with no co-author lines. MIT licence for the code; weights and PlantSeg-derived material are
  CC BY-NC 4.0. The private working repository and its history are unchanged.
- Hugging Face now needs PRO to host Gradio Spaces (402 on upload), so the live demo is a Colab notebook instead.
  Also added: a GIF and a retake screenshot, a run-it-yourself section, and the region checkpoint shipped in the
  public repository.
- The public repository was made public on 2026-11-23, at Adrija's request.

## 2026-11-23 — Phase 8 step 1: phone-sized leaf finders (tuning images only, no gold)

- Adrija approved three candidates and their downloads. Both repos are Apache 2.0 and were fetched at pinned
  commits to `data/third_party/` (gitignored):
  - MobileSAM `f706ad9c` (mobile_sam.pt SHA-256 6dbb9052...);
  - EfficientSAM-Ti `d525f622` (the authors' ONNX encoder 84ed466f... and decoder a62f8fa5...);
  - tap + box GrabCut (no model).
- Exports (`src/mobile/export_leaf_models.py`, written to `data/mobile_models/`, gitignored):
  - MobileSAM: encoder (1024 input) plus a decoder that returns SAM's 4 low-resolution masks; the upsampling is
    done outside the model, so the decoder does not depend on the photo size.
  - INT8: dynamic MatMul/Gemm only, the same reason as for SegFormer.
- Rule: every SAM-style finder uses the FROZEN `min_area` rule on its 3 multimask candidates (MobileSAM masks 1-3).
  So only the model changes, not the rule.
- Comparison (`src/mobile/compare_leaf_finders.py`):
  - images: the 12 rated tuning images with Adrija's clicks, plus the rest of the tuning queue with the automatic
    click; the script refuses any gold name;
  - reference: the SAM 2 tiny leaf (final-v1), not ground truth;
  - severity uses the same region and colour rule, so only the leaf changes.
- GrabCut fix (before the full run): the first version marked everything outside the automatic box as definite
  background. On long leaves that put the leaf's own colour into the background model, and GrabCut returned only
  the tap disc (found with a synthetic test). Now outside the box is probable background and only a thin image
  border is definite background.
- Results (run `experiments/20261123_125054_leaf_finders`, `report/tables/leaf_finders.md`, sheets in
  `report/figures/leaf_finders/`):
  - all 78 tuning images, median leaf IoU with SAM 2 / same placeholder level: MobileSAM INT8 0.97 / 88%,
    EfficientSAM-Ti INT8 0.96 / 94%, GrabCut 0.54 / 74%;
  - rated 12, worst severity change: MobileSAM INT8 37.7 points, EfficientSAM INT8 11.5, GrabCut 44.9;
  - size: MobileSAM INT8 26.9 MB, EfficientSAM INT8 17.8 MB;
  - laptop speed at 4 threads (encoder + decoder): MobileSAM INT8 366 + 29 ms, EfficientSAM INT8 822 + 30 ms,
    SAM 2 tiny 1085 + 48 ms.
- The run stopped for the GrabCut fix (`experiments/20261123_125027_leaf_finders`, config only) was deleted.
- Checkpoint: waiting for Adrija's choice of leaf finder.

## 2026-11-23 — Phase 8 decision: leaf finder for the mobile version (Adrija)

- **Chosen: EfficientSAM-Ti INT8** (dynamic MatMul/Gemm; 17.8 MB), with the frozen `min_area` rule on its 3
  candidates. Reason: the comparison table `report/tables/leaf_finders.md` and the contact sheets
  `report/figures/leaf_finders/rated.png` and `queue_worst.png` (run `experiments/20261123_125054_leaf_finders`).
  It agrees best with the frozen SAM 2 leaf: same placeholder level on 94% of the 78 tuning images and 12/12 rated.
  Its worst severity change on the rated set is 11.5 points (MobileSAM INT8: 37.7). It is also the smallest file.
  Cost: an encoder about twice as slow as MobileSAM's on the laptop CPU.
- **Fallback rule, fixed now, before any phone measurement:** if the full app takes more than 10 s per photo on
  the test phone (or a low-RAM emulator if there is no phone), switch to MobileSAM INT8 and log it.
  GrabCut is not used.

## 2026-11-23 — Phase 8: browser pipeline and parity test

- **Region model:** SegFormer-B0 INT8 *dynamic* (7.8 MB), not static (4.5 MB). Its region agreement with FP32 is
  0.978, against 0.911 for static (`report/tables/export.md`), so the mobile version stays closer to final-v1.
  WebAssembly speed is about the same (1 thread: 1.6 s vs 1.9 s).
- **Port:** `app/web/js/pipeline.js` is a pure module that runs in the browser and in Node.
  - Every frozen value comes from `app/web/policy.json` (`python -m src.mobile.export_web_policy`).
  - cv2 is reproduced where it matters: INTER_AREA tables, the fixed-point RGB2GRAY and RGB2HSV, and the 11-bit
    INTER_LINEAR.
  - Python reference: `src/mobile/pipeline_ref.py` (final-v1 code with the two phone models).
- **Parity test** (`src/mobile/parity.py` + `app/parity/run_parity.mjs`), clean test split, 121 images, with the
  final-v1 automatic click as the tap. Adrija asked for it on the test images. Nothing is tuned on them.
- **WebAssembly speed** (Node, onnxruntime-web 1.20.1, laptop CPU, best of 2 runs):
  - 1 thread: SegFormer INT8 1.6 s; EfficientSAM-Ti encoder INT8 6.0 s, FP32 23 s; MobileSAM encoder INT8 2.5 s;
  - 4 threads: SegFormer INT8 0.20 s; EfficientSAM encoder INT8 2.1 s; MobileSAM encoder INT8 0.84 s;
  - full pipeline, 1 thread: about 6.5 s per photo (encoder 5.8 s);
  - a first run measured 20 s while another process loaded the CPU; the re-run gave 6.5 s.
- **Definition for the 10 s fallback rule**, fixed before any phone measurement: compute time per photo measured
  inside the app = gate + region + leaf encoder + leaf decoder + colour rule and uncertainty. User time (choosing
  the disease, tapping) is not counted, and nor is model loading on first start (reported separately).
- **Speed plan:** WebAssembly threads need cross-origin isolation. The app's service worker adds COOP/COEP headers
  (GitHub Pages cannot set headers), and the leaf encoder starts as soon as the photo is chosen.

## 2026-11-23 — Phase 8: parity result (the "mobile version" numbers)

- Table: `report/tables/mobile_parity.md`; clean test split, 121 images, final-v1 automatic click as the tap.
- **Mobile version (browser) vs final-v1:** severity difference mean 2.23 / median 0.11 / 95th pct 9.3 / max
  35.8 points; within 1 point on 74%; same placeholder level 88%; same decision 88%; same gate result 100%;
  same action (answer / consult / retake) 93%. Answer / consult / retake rates 70 / 22 / 7% (final-v1 70 / 22 / 7%).
- Almost all of the gap comes from the phone models, not the port: mobile (Python) vs final-v1 is 2.16 / 0.09 /
  9.2 / 35.7 points, 88% same level. Leaf masks EfficientSAM vs SAM 2: median IoU 0.94, 54 images below 0.9,
  lowest 0.016 (a different leaf picked).
- **Porting error** (browser vs Python mobile): mean 0.15, max 3.1 points; 100% same level, decision and gate;
  99% same action. Region IoU median 0.992, leaf IoU median 0.996. Largest gate-feature difference: noise, 1%.
- Speed in Node, 1 thread, laptop: median 6.6 s per photo (encoder 5.8 s).

## 2026-11-23 — Phase 8: app (PWA + Android), routine decisions

- **Two stages:** `analysePhoto` (gate, region, leaf encoder) runs as soon as the photo is chosen; `finishAnalysis`
  (decoder, colour rule, uncertainty) runs on the tap. `analyse` chains both, so the parity runner tests the same
  code. `computeMs` = stage 1 + stage 2, without the farmer's choosing time (the 10 s rule definition above).
- **Gate failure** stops after stage 1 and shows "retake" without asking for the disease or tap (faster, same
  outcome as final-v1, which returns retake before looking at the leaf).
- **Pipeline in a Web Worker** so the screen stays responsive; one model run at a time.
- **Model files are checked** against the sha256 in `policy.json` when loaded.
- **Service worker:** precaches the app (37.2 MB: models 25.5 MB, WebAssembly runtime 11 MB) with a progress bar on
  first visit, then reloads once with COOP/COEP so threads work. Threads = min(4, cores - 1).
- **Fonts:** Noto, self-hosted from pinned @fontsource 5.3.0 (OFL), weights 400 + 700, one script subset each.
  Only Latin is precached; a script font is downloaded when its language is chosen (1.04 MB for all 13 scripts).
  The language picker loads all of them so each name shows in its own script.
- **Speech:** Web Speech API in browsers; in the APK the @capacitor-community/text-to-speech 4.1.1 plugin, called
  through the Capacitor bridge (no bundler). When no voice exists the card says so ("no_voice").
- **APK:** Capacitor 6.2.3 built by GitHub Actions (debug-signed, for sideloading). `MainActivity` routes service
  worker requests to Capacitor's local server; without this, service workers (and so threads) do not work in the
  APK. Not yet verified on a phone.
- **Translations:** `app/web/strings.json`, 37 phrases x 22 languages + English, all non-English marked
  `machine_draft` with a draft-confidence hint (lowest: Santali, Manipuri, Bodo). Review sheet:
  `report/tables/translation_review.csv` (`python -m src.mobile.review_sheet`). CSV, not XLSX, to avoid a new
  dependency (opens in Excel and Google Sheets).
- **Browser test** (`app/parity/ui_test.py`, Chromium, Pixel 5 size, laptop CPU): isolated = true, 4 threads,
  stripe-rust example -> treat, 10.5% (centre tap, not the demo's tap); compute 3.1 s (encoder 2.5 s); offline
  reload works; Hindi, Urdu (RTL) and Santali render. Screenshots: `report/figures/app/`.
  reload works; Hindi, Urdu (RTL) and Santali render. Screenshots: `report/figures/app/`.
- Re-check after the two-stage refactor: the JavaScript side was re-run on all 121 images; action, severity,
  level, decision, uncertainty and failed checks are identical on 121/121.
- APK: GitHub Actions run 45142731297 on the public repo, debug APK 29.1 MB, sha256 fee24a53…4109.
  Pages run 45142731857 failed only because Pages is not yet enabled (Settings step for Adrija).
