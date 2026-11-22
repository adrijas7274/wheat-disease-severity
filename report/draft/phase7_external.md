# Draft report section: External wheat field photos (Phase 7)

Draft written 2026-11-17 from `experiments/LOG.md`, `report/tables/phase7_mendeley.md` and
`report/dataset_versions.md`. TODO marks things still to be checked or filled in.

## Methods

**Why not PlantDoc.** The plan named PlantDoc as the unseen field set, but PlantDoc has no wheat
classes (28 classes over 13 other crops). Two wheat field sets were used instead. Neither was
used for training or tuning.

**Mendeley Wheat Leaf Dataset** (Getachew, 2021; CC BY 4.0; DOI 10.17632/wgd66f8n6h.1). 407
field photos from Holeta, Ethiopia, taken with a Canon EOS 5D Mark III and sorted with plant
pathologists into stripe rust (208), septoria (97) and healthy (102). One photo is a
byte-identical copy and was counted once (406 photos). Labels are image level only, so these
checks cannot measure severity error; they test whether the pipeline behaves sensibly on photos
from a new source:
- healthy leaves: share estimated at exactly 0% and at most 1%, and the distribution of the false
  severity. A healthy leaf has no disease to choose the colour rule, so all three rules (rust,
  necrotic, mildew) are reported;
- diseased leaves: share detected (> 0%) and the severity distribution per disease (rust rule for
  stripe rust, necrotic rule for septoria);
- the Phase 6 v2 gate and policy (post hoc): share sent back for a retake, referred to an expert,
  and answered.

The whole final pipeline runs on every photo at full resolution: SegFormer-B0 infected region,
the automatic click (deepest point of the largest predicted component, image centre if none),
SAM 2 leaf, the Phase 5 colour stage (denoise, shades-of-gray, exposure; thresholds rust 5,
necrotic 15, mildew 8), and the Phase 6 v2 gate ranges, classifier and thresholds, unchanged.
Shares have bootstrap 95% CIs over photos. Levels and decisions use the **placeholder**
thresholds.

**Photo size.** Every photo is downscaled (area interpolation) to a long side of at most 2048 px
before the pipeline. This was decided for memory and runtime after repeated out-of-memory stops at
6000 x 4000, before any full-run result; the app will downscale photos anyway.

**NWRD** (Sensors 2023; 100 stripe rust field photos with binary rust masks) was planned for an
infected-region IoU check. **Attempted, not used:** the download site was unreachable and no data
licence is stated (the paper is CC BY 4.0 and the code MIT, but neither covers the data).

## Results

Mendeley, 406 photos (`report/tables/phase7_mendeley.md`; figure `report/figures/phase7/mendeley_severity.png`;
example overlays in `report/figures/phase7/overlays/`). Shares with bootstrap 95% CIs.

| class | colour rule | n | exactly 0% | at most 1% | detected (> 0%) | median severity (IQR) | p90 |
|---|---|---:|---|---:|---|---|---:|
| healthy | rust | 101 | 68% (59-77%) | 88% | 32% | 0.0 (0.0-0.1) | 1.1 |
| healthy | necrotic | 101 | 93% (88-97%) | 100% | 7% | 0.0 (0.0-0.0) | 0.0 |
| healthy | mildew | 101 | 45% (36-54%) | 73% | 55% | 0.0 (0.0-1.2) | 7.2 |
| stripe rust | rust | 208 | 27% | 38% | **73% (66-78%)** | 2.8 (0.0-7.7) | 13.5 |
| septoria | necrotic | 97 | 94% | 94% | **6% (2-11%)** | 0.0 (0.0-0.0) | 0.0 |

**Healthy leaves.** With the rust and necrotic rules, false severity is small: 88% and 100% of
healthy leaves are at most 1%. The mildew rule gives false severity on 55% of healthy leaves, up to
80% (8 of 101 reach the "high" level). Pale, bright healthy tissue looks like mildew to that rule.

**Stripe rust** is detected on 73% of photos, with a median of 2.8% and 90% below 13.5%.

**Septoria is almost never detected (6%).** The region model finds an infected region on every
septoria leaf (median 68% of the leaf), but the necrotic colour rule marks nothing inside it on 94%
of photos, including leaves with large tan blotches. A diagnostic, run after this result and not
used to choose anything, re-ran the same photos with the Phase 3 colour stage (no preprocessing):
84% detected, median 37.9%. **The Phase 5 colour stage causes the misses.** The saved Phase 5
records show the same on PlantSeg. On clean septoria photos the share at exactly 0% rises from
29% to 50% on test and from 19% to 62% on validation, and for bacterial leaf streak from 47% to
65% on test. Phase 5 checked only the overall zero share (27% against 28%), which hid this,
because powdery mildew moved the other way (21% to 7%).

**Gate and policy on clean new-source photos** (Phase 6 v2): the gate sends back 25% of healthy
photos (blurred 12%, noisy 11%, exposure 7%), 12% of stripe rust and 4% of septoria photos.
"Consult an expert" fires on 0-7% at the 80% target. The policy does not flag the septoria misses:
91% of septoria photos are answered, almost all with 0% ("no action").

**NWRD:** attempted, not used (download site unreachable, no data licence stated).

**Gap recovered.** The plan asked how much of the lab-to-field and clean-to-corrupted gap was
recovered. Neither can be measured here: the Mendeley labels are image level, and no PlantDoc-style
wheat set with masks was available. TODO: answer this from own phone photos with ratings.

## Results: final pipeline on Mendeley (NOT INDEPENDENT)

The results above use the Phase 5 v1 colour stage and are kept unchanged. After Phase 5 v2
(no preprocessing for any group) and the Phase 6 v2 rules re-fitted on it (policy score:
photometric TTA spread), the same 406 photos were re-run with the final pipeline. **This is not an
independent test**: the necrotic problem that led to Phase 5 v2 was found on this set. Table:
`report/tables/phase7_mendeley_final.md`.

| class | colour rule | detected (> 0%), v1 stage -> final | median severity, final | retake / consult / answered (80%), final |
|---|---|---|---|---|
| septoria blotch | necrotic | 6% -> 84% | 37.9% | 4% / 45% / 51% |
| stripe rust | rust | 73% -> 96% | 7.4% | 12% / 14% / 74% |
| healthy | rust | 32% -> 14% | 0.0% | 25% / 1% / 74% |
| healthy | necrotic | 7% -> 9% | 0.0% | 25% / 1% / 74% |
| healthy | mildew | 55% -> 36% | 0.0% | 25% / 2% / 73% |

Healthy leaves at a "high" level under the mildew rule: 8 -> 4 of 101 (max 59%). The final
pipeline detects both diseases on this source, but sends 45% of septoria photos to "consult an
expert" at the 80% target.

## Results: JIC wheat disease images (independent, single evaluation)

JIC (Long, Hartley, Morris & Brown, 2023; Zenodo 7573133, CC BY 4.0): 999 field photos, not
downloaded until the final pipeline was tagged `final-v1`, evaluated once. Class mapping fixed
before download (yellow rust -> stripe rust, brown rust -> leaf rust, septoria, mildew -> powdery
mildew, healthy). Same pipeline and 2048 px cap as above. Table: `report/tables/phase7_jic.md`.

| class | n | colour rule | detected (> 0%) (95% CI) | median severity (IQR) | high level | retake / consult / answered (80%) |
|---|---:|---|---|---|---:|---|
| stripe rust | 239 | rust | 82% (77-86%) | 4.2% (0.3-15.2) | 47 | 6% / 19% / 74% |
| leaf rust | 128 | rust | 88% (81-93%) | 4.8% (0.2-20.2) | 33 | 3% / 15% / 82% |
| septoria blotch | 349 | necrotic | 58% (53-64%) | 0.5% (0.0-9.2) | 49 | 3% / 16% / 81% |
| powdery mildew | 161 | mildew | 80% (73-85%) | 2.2% (0.0-15.6) | 35 | 4% / 18% / 78% |
| healthy | 122 | rust | 29% (21-36%) false | 0.0% (0.0-0.1) | 10 | 5% / 8% / 87% |
| healthy | 122 | necrotic | 20% (14-28%) false | 0.0% (0.0-0.0) | 7 | 5% / 6% / 89% |
| healthy | 122 | mildew | 63% (54-72%) false | 0.1% (0.0-1.6) | 8 | 5% / 10% / 85% |

- **Detection:** the rust rules detect 82-88% of rust photos and the mildew rule 80%; septoria is
  the weakest, 58% (42% answered exactly 0%), lower than on Mendeley (84%).
- **Healthy false alarms:** the median is 0% under every rule, but the mildew rule gives a
  severity above 0% on 63% of healthy leaves, and 7-10 of 122 healthy leaves reach the "high"
  level under each rule. Abstention does not remove them: answered healthy estimates still reach
  88% (rust rule) and 76% (necrotic rule).
- **Gate and policy:** these photos are mostly clean, so only 3-6% are sent back; 6-19% go to
  "consult an expert" at the 80% target.
- The SAM 2 leaf from the automatic click covers a median 4-8% of the photo (Mendeley 10-13%),
  so the click often lands on a small leaf or leaf part in a crowded canopy.

## Limitations

- **Image-level labels only:** detection rates and false severity on healthy leaves, not severity
  error. A detected stripe rust estimate may still be far from the true severity.
- **The Phase 5 v1 colour stage fails on septoria from a new source**, and on PlantSeg it raises
  the zero share for both necrotic diseases. Phase 5's v1 stability result for necrotic diseases is
  partly an artefact of answering 0%. Corrected post hoc by Phase 5 v2 (no preprocessing); the
  final-pipeline Mendeley numbers are therefore not independent, and JIC is the independent check.
- The septoria diagnostic was run after seeing the result, on the evaluation set. It explains the
  failure; it must not be used to pick a colour stage.
- Healthy leaves have no disease to choose the colour rule, so the false-severity result depends on
  which rule the app would use. The mildew rule is the least specific.
- **Mildew false alarms on healthy leaves.** With the Phase 5 v1 stage the mildew rule gives a
  severity above 0% on 55% of healthy Mendeley leaves (8 of 101 at "high"); with the final pipeline
  36% (4 of 101 at "high"), and 31% of the 250 Bangladesh healthy originals. Pale, bright healthy
  tissue looks like mildew to the colour rule. A farmer photographing a healthy leaf under the
  mildew rule may be told to monitor or treat.
- One source (one farm in Ethiopia, one camera); photos downscaled to 2048 px.
- The gate's ranges come from 78 PlantSeg validation photos; 25% of healthy field photos are sent back.
- NWRD not used, so there is no external pixel-level region check.
- Placeholder levels, decisions and coverage targets; one region model, one seed.
- **JIC (independent):** septoria detection is 58%, and healthy leaves get false severity, most often
  under the mildew rule (63% above 0%), with 6-8% at "high" under each rule even after abstention.
  The healthy result depends on which rule the app would run, which needs a disease classifier or
  the farmer's choice; neither was evaluated. JIC photos are of crowded canopies, where the
  automatic click picks small leaf regions; in the app the farmer taps the leaf instead.
