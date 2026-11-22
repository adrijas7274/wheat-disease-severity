# PlantSeg v6 vs v7: dataset version comparison

**Date:** 2026-10-01
**Decision:** use **v7** (Zenodo record [17719108](https://zenodo.org/records/17719108)). v6 (record [16665770](https://zenodo.org/records/16665770)) is archived at `data/archive/plantseg_v6` and must never be used for training or evaluation.

This document records why. All numbers below were regenerated directly from
the two extracted dataset folders (not transcribed by hand) so they can be
reproduced from `Metadata.csv` in each version.

## Background

The project plan originally specified PlantSeg v6 (record 16665770) as a licence
CC BY-NC-ND 4.0 dataset. Checking the actual Zenodo record showed two things
were wrong:

1. v6's real licence is **CC BY 4.0**, not CC BY-NC-ND.
2. v6 is not the latest version. The concept DOI (10.5281/zenodo.13293890)
   has 7 version records; **v7 (17719108, published 2025-11-25) postdates
   v6 (16665770, published 2025-07-31)** and was not mentioned anywhere in
   the project plan or discovered until explicitly checking the Zenodo version
   history.

v7 has **no public changelog**. The PlantSeg GitHub repo
([tqwei05/PlantSeg](https://github.com/tqwei05/PlantSeg)) has no commits
since 2025-03-25 and its README still links the older v4 record
(14935094) - v7 is an undocumented, Zenodo-only revision. Everything below
is inferred from the data itself, not from any statement by the authors.

## Headline numbers

| | v6 (16665770) | v7 (17719108) |
|---|---|---|
| Total images | 11,458 | 7,774 (-32%) |
| Train / Val / Test | 7,916 / 1,247 / 2,295 | 5,367 / 846 / 1,561 |
| Disease classes present | 114 of 115 (**"soybean rust" has 0 images**) | 115 of 115 |
| Dataset-level licence | CC BY 4.0 | CC BY-NC 4.0 |
| Per-image `License` tag | 1,133 CC-BY / 10,325 CC0 | 7,741 CC-BY-NC / 33 CC0 |
| Median resolution (W x H) | 667 x 534 | 650 x 520 |
| Resolution range (W x H) | 65x52 - 8256x5504 | 93x87 - 6000x5408 |
| Mean / median mask ratio | 0.2136 / 0.1366 | 0.2136 / 0.1386 |
| Image/mask counts per split | match exactly | match exactly |

Image and mask file counts match exactly per split in both versions - no
orphaned images or masks in either.

## Filenames are not stable identifiers across versions

All 7,774 v7 filenames also exist as filenames in v6 (same
`plant_disease_index.jpg` naming convention), but filename equality does
**not** mean image equality:

| | count |
|---|---|
| v7 filenames that also exist in v6 | 7,774 / 7,774 (100%) |
| ...of those, same source URL (genuinely the same photo) | 1,783 (23%) |
| ...of those, different source URL (same name, different photo) | 5,991 (77%) |

**Any comparison methodology that assumes "same filename = same image" is
wrong for this dataset.** The index numbers were reused for different
underlying photos when the authors re-curated for v7.

## Where images do genuinely carry over, nothing was reprocessed

For all 1,783 image pairs confirmed to share the same source URL (a valid
same-image control group), both images were checked byte-for-byte:

| | identical | different | missing |
|---|---|---|---|
| Image files | 1,783 | 0 | 0 |
| Mask files | 1,783 | 0 | 0 |

100% byte-identical, both image and mask, for every single genuinely-shared
pair - this was a full check (all 1,783 pairs), not a sample. Mask-ratio
metadata matched exactly too. **Conclusion: v7 did not recompress, resize,
or re-annotate any retained image.** The entire difference between versions
is which images are included, not how they were processed.

## What was removed vs. kept - by licence tag

Of the 11,458 v6 rows, 1,952 are retained in v7 (by source URL) and 9,506
were dropped.

| | retained (1,952) | removed (9,506) |
|---|---|---|
| CC-BY | 991 | 142 |
| CC0 | 961 | 9,364 |

At face value this looks licence-driven (CC0-tagged images were
overwhelmingly removed). But the per-image `License` column in v6 skews
90% CC0 overall, so a large CC0 removal count is partly just because CC0
dominates v6's CSV in the first place - this table alone doesn't prove
licence was the deciding factor. The domain breakdown below is more telling.

## What was removed vs. kept - by source domain

Retention rate for the domains with the most v6 occurrences:

| domain | kept / total | retention |
|---|---|---|
| www.sohu.com | 211 / 219 | 96% |
| www.360doc.com | 204 / 216 | 94% |
| baijiahao.baidu.com | 191 / 238 | 80% |
| www.forestryimages.org | 25 / 278 | 9% |
| www.researchgate.net | 33 / 494 | 7% |
| www.invasive.org | 17 / 403 | 4% |
| www.ipmimages.org | 12 / 232 | 5% |
| www.flickr.com | 15 / 450 | 3% |
| en.wikipedia.org | 5 / 201 | 2% |
| www.reddit.com | 4 / 510 | 1% |
| commons.wikimedia.org | 4 / 485 | 1% |
| www.agric.wa.gov.au | 3 / 250 | 1% |
| plantix.net | 0 / 227 | 0% |
| www.youtube.com | 0 / 173 | 0% |
| www.gardeningknowhow.com | 0 / 164 | 0% |

Chinese blog/social platforms (Sohu, 360doc, Baidu) were retained at
80-96%. Scientific/archival sources (Wikimedia Commons, ResearchGate,
Flickr, Reddit, invasive.org, forestryimages.org, ipmimages.org,
government agriculture sites) were retained at 0-9%.

This cuts against a simple "licence compliance cleanup" story - if
anything, the *better-documented* sources (government/academic archives
with clear attribution) were removed, and the *less-documented* ones
(casual blog reposts) were kept. A more plausible read: PlantSeg's stated
goal is "in-the-wild" images, and sources like invasive.org / ipmimages.org
/ forestryimages.org are classic clean, single-leaf diagnostic reference
photography (closer to PlantVillage-style lab images) rather than true
field conditions. v7 may be curating toward field realism and away from
archival reference shots. **This is inference from the retention pattern,
not a confirmed statement from the authors** - no changelog exists to
verify intent.

## Per-class impact

Every one of the 115 disease classes shrank from v6 to v7 **except one**:

| class | v6 | v7 | delta |
|---|---|---|---|
| soybean rust | 0 | 66 | **+66** |

`soybean rust` is a defined class in PlantSeg's own taxonomy
(`plantseg115.py`) that had **zero images in v6** - anyone training on all
115 classes with v6 would have had no training signal at all for this
class. v7 fixes that.

The 10 largest absolute drops (all other classes fall between these and
the near-zero-change entries):

| class | v6 | v7 | delta |
|---|---|---|---|
| bean rust | 233 | 75 | -158 |
| wheat stripe rust | 358 | 228 | -130 |
| wheat powdery mildew | 271 | 178 | -93 |
| apple scab | 258 | 168 | -90 |
| wheat septoria blotch | 232 | 142 | -90 |
| wheat head scab | 319 | 230 | -89 |
| soybean frog eye leaf spot | 238 | 153 | -85 |
| zucchini powdery mildew | 213 | 133 | -80 |
| banana bunchy top | 157 | 78 | -79 |
| peach brown rot | 173 | 96 | -77 |

## Candidate crop totals (images), v6 -> v7

| crop | v6 | v7 |
|---|---|---|
| wheat | 1,792 | 1,166 |
| tomato | 901 | 667 |
| maize/corn | 616 | 419 |
| banana | 573 | 354 |
| grape | 564 | 400 |
| chilli/pepper (bell pepper only - no true chilli in PlantSeg) | 247 | 176 |
| potato | 243 | 146 |
| rice | 159 | 105 |
| cotton | 0 | 0 |
| mango | 0 | 0 |

No candidate crop disappears in v7; all shrink by roughly the dataset-wide
~25-35%. **Cotton and mango have zero PlantSeg images in either version**
and would need a separate crop-specific dataset if chosen. Rice and potato
were already the thinnest viable candidates in v6 and are thinner still in
v7.

## Decision rationale

Chosen: **v7**. Reasoning:
- v7's licence (CC BY-NC 4.0) does not block an academic/thesis project;
  the non-commercial restriction only matters if this work is later
  commercialised, at which point the data would need revisiting regardless.
- v6's licence claim (CC BY 4.0, and 90% of its own per-image tags marked
  CC0) looks optimistic for images scraped from arbitrary blog/social
  posts - v7's more conservative tagging is more credible, even though the
  underlying cause looks more like a source-type curation shift than a
  rigorous per-image licence audit (see domain analysis above).
- The ~32% data loss is real and worth tracking, particularly for rice and
  potato, but no candidate crop is eliminated.
- v6 remains archived (`data/archive/plantseg_v6`) for reference, not for
  use - mixing the two would leak 1,783 duplicated images across whatever
  splits each version assigns them to.

## Caveats

- No PlantSeg changelog exists for v7; the domain-retention interpretation
  above is this project's inference from the data, not a confirmed fact
  from the dataset authors.
- JPEG-quality was compared only via a rough proxy (mean of the JPEG
  luminance quantization table on a 40-image sample per version), not a
  calibrated quality percentage. Both versions showed the same median
  value (29.0), consistent with no compression change.

## Dataset quality: duplicate photos and label conflicts (v7, wheat)

Checked on 2026-11-14 with `python -m src.data.near_duplicates` (64-bit dHash,
at most 6 bits apart, plus a 32 x 32 thumbnail test). Full pair list:
`report/tables/near_duplicates.md`. Scope: the 706 PlantSeg v7 images of the
five wheat leaf-disease classes (480 train, 86 val, 140 test).

| finding | count |
|---|---:|
| near-duplicate pairs | 83 (in 71 groups) |
| pairs across a split boundary | 48 |
| train / test pairs | 28 (26 with both images in the Phase 2 sets) |
| train / val pairs | 18 |
| val / test pairs | 2 |
| pairs inside one split | 35 (30 train, 5 test) |
| pairs with two different disease labels | 12 |

- **The official split leaks.** PlantSeg's train / val / test split puts copies
  of the same photo on both sides. For wheat, 22 Phase 2 test images and 17
  Phase 2 validation images had a copy in training.
- **Labels conflict.** 12 pairs give the same photo two disease names, mostly
  septoria blotch against bacterial leaf streak and stripe rust against leaf
  rust. Labels were not changed.
- **Masks conflict.** The two masks of a duplicated photo often differ (median
  IoU 0.83 over the 26 train / test pairs, lowest 0.18).
- **This is a lower bound.** The hash check finds resized and re-compressed
  copies only. Crops, mirrored or rotated copies, heavily watermarked copies
  and separate photos of the same leaf are not found. Only wheat was checked.

**What this project does about it** (decided 2026-11-14): the official test and
val sets are kept, 70 training images and 2 validation images are removed
(`configs/split_exclude.yaml`, with a reason per image), and both baselines
were retrained. We are still using the official split in the sense that no
image changes split; images are only removed. Whether the PlantSeg authors
know about the duplicates is unknown; nothing about them was found in the
dataset documentation we have (TODO: check the paper and the Zenodo record
again before the final report).


---

# External wheat field sets for Phase 7 (recorded 2026-11-17)

PlantDoc, the planned unseen field set, has **no wheat classes** (28 classes over 13 other crops; checked on
github.com/pratikkayal/PlantDoc-Dataset, 2026-11-17; licence CC BY 4.0). Adrija chose two wheat sets instead.
Both are used **only for evaluation, never for training or tuning**.

## Mendeley Wheat Leaf Dataset

| | |
|---|---|
| Source | Mendeley Data, https://data.mendeley.com/datasets/wgd66f8n6h/1 |
| DOI | 10.17632/wgd66f8n6h.1 (version 1, published 2021-08-03) |
| Contributor | Hawi Getachew, Admas University (no other authors listed on the page) |
| **Licence** | **CC BY 4.0**: research use allowed, attribution required |
| Contents (as stated on the page) | 208 stripe rust, 97 septoria, 102 healthy leaf photos; Holeta wheat farm, Ethiopia; uncontrolled field conditions; Canon EOS 5D Mark III; classes assigned with plant pathologists |
| Labels | image level only (no masks, no boxes, no severity) |
| File | `wheat_leaf.rar`, 1,511,923,897 bytes, SHA-256 `23653dd88f9f900315a9a0c88a163c891b3bdd00cc89b36d98cc5b3fcc1d7e94` (from the Mendeley public API) |
| Local path | `data/raw/mendeley_wheat_leaf/` (archive), extracted to `data/raw/mendeley_wheat_leaf/extracted/` |

## NWRD (NUST Wheat Rust Disease)

| | |
|---|---|
| Paper | "The NWRD Dataset: An Open-Source Annotated Segmentation Dataset of Diseased Wheat Crop", Sensors 2023, 23(15):6942, DOI 10.3390/s23156942 |
| Paper licence | CC BY 4.0 (article) |
| Code | https://github.com/dll-ncai/NUST-Wheat-Rust-Disease-NWRD, MIT licence ("Copyright (c) 2023 Technische Universität Kaiserslautern (TUK) & National University of Sciences and Technology (NUST)"); the licence text covers the software only |
| **Dataset licence** | **Not stated** on any page that could be read. The paper calls the dataset open source; the README gives the download page https://dll.seecs.nust.edu.pk/downloads/, which refused connections on 2026-11-17 (https and http), so its terms could not be read |
| Contents (README / paper) | 100 stripe rust field photos (.jpg), binary masks (.png); 4608 x 3456 (a few 6016 x 4000); train/test folders; mask colour convention not stated |
| Local path | `data/raw/nwrd/` (not downloaded) |

**Status: attempted, not used** (Adrija, 2026-11-18): download site unreachable and no data licence stated.

## Mendeley processing note

All Mendeley photos are downscaled (area interpolation) to a long side of at most 2048 px before the
pipeline (Adrija, 2026-11-18): decided for memory and runtime after repeated out-of-memory stops at
6000 x 4000, before any full-run result; the app will downscale photos anyway.

---

# Healthy guard set and reserved external test for Phase 5 v2 (recorded 2026-11-18)

**Why not PlantSeg's own healthy images:** PlantSeg has none. It is a disease-segmentation dataset: all 7,774
v7 images carry one of 115 disease labels (no label contains "healthy"), and all 1,166 wheat images (8 wheat
diseases) have a non-empty lesion mask (`Mask ratio` > 0). Checked in `Metadata.csv` on 2026-11-18.

## Bangladesh wheat set (healthy guard for Phase 5 v2 only)

| | |
|---|---|
| Title | "Disease Dataset of Wheat: Original, Augmented, and Balanced for Deep Learning" |
| Source | Mendeley Data, https://data.mendeley.com/datasets/5gc7hwydwg/1 |
| DOI | 10.17632/5gc7hwydwg.1 (published 2025-03-05) |
| Contributors | Md Istiak Rahman Radowan, Rokonozzaman Ayon Ayon |
| **Licence** | **CC BY 4.0** (Mendeley API licence record): research use allowed, attribution required |
| Contents (as stated) | wheat crop field in Bangladesh; 1,603 original 1920 x 1080 photos: black point 303, fusarium foot rot 250, **healthy leaf 250**, leaf blight 400, wheat blast 400; plus augmented copies |
| **Use** | **original healthy leaf photos only**, for the Phase 5 v2 healthy false-alarm guard (G3). Never the augmented copies; never for training; the disease classes are not used |
| File | `Wheat Disease.zip`, 3,817,584,463 bytes, SHA-256 `bb21be5d9dbfb9a543231fb9e3882901248b8c9cd3201a98169eb364e9278196` (Mendeley API) |
| Local path | `data/raw/bangladesh_wheat/` (archive), extracted to `data/raw/bangladesh_wheat/extracted/` |

## JIC wheat disease images (reserved external test)

| | |
|---|---|
| Title | "Wheat disease images (small dataset)" |
| Source | Zenodo, https://zenodo.org/records/7573133 |
| DOI | 10.5281/zenodo.7573133 (published 2023-01-26) |
| Creators | Megan C. Long, Matthew Hartley, Richard J. Morris, James K. M. Brown (John Innes Centre) |
| **Licence** | **CC BY 4.0** (Zenodo record metadata): research use allowed, attribution required |
| Contents (as stated) | 999 wheat images "taken in realistic growth conditions": yellow rust, brown rust, septoria, mildew, healthy; subset of a 19,172-image collection (full set on request). Per-class counts not stated |
| File | `Long 2023 Plant Path 999 photos.zip`, 1,029,380,819 bytes |
| **Rule (Adrija, 2026-11-18)** | not downloaded or looked at until Phase 5 v2 and the re-fitted Phase 6 policy are frozen and tagged; then evaluated **once** |
| **Class mapping (fixed before the run)** | yellow rust -> wheat stripe rust (rust rule); brown rust -> wheat leaf rust (rust rule); septoria -> wheat septoria blotch (necrotic rule); mildew -> wheat powdery mildew (mildew rule); healthy -> healthy (all three rules reported) |
| Download (2026-11-21, after tag `final-v1`) | `data/raw/jic_wheat/jic.zip`, MD5 `1f8a7c660c2da137b957fb4edee3dd7d` (matches Zenodo) |
| Layout | 999 PNG files in one flat folder; class in the file name: Septoria 349, YellowRust 239, Mildew 161, BrownRust 128, Healthy 122. Extracted into one folder per file-name prefix (`data/raw/jic_wheat/extracted/<prefix>/`) so the fixed keyword mapping applies unchanged |
