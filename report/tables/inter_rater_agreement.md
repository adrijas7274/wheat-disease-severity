# Inter-rater agreement: Claude vs. original human tags

Date: 2026-10-03T10:34:43.111918+00:00
Sample: 64 images (30 random close_up + all original wide/non_photo/skip), tags hidden during review
Agreement: 28/64 (43.8%)
Cohen's kappa: -0.006

This is a genuinely low agreement, not a data error (see summary below the table) -
the disagreement is concentrated almost entirely on the wide category.

**Caveat added 2026-10-04 (Adrija's correction):** treat Claude's blind
tags in this check as a low-confidence second opinion, not ground truth.
Two pieces of evidence: (1) Claude called 10 of the 11 original non_photo
images close_up here - a near-total miss on that category; (2) Claude's
own earlier qualitative estimate from a 30-image contact sheet during crop
selection put bacterial leaf streak at ~35-40% wider/medium framing, but
Claude's full review of all 83 bacterial leaf streak images (same reviewer,
same guidelines, different pass) found zero wide-worthy images. Those two
Claude-produced numbers contradict each other, which means Claude's own
framing judgment is not stable across viewing contexts and should not be
weighted as equal to - let alone above - the human's original tag. See
`disputed` column in `data/processed/wheat_tags.csv` and the 2026-10-04
entry in `experiments/LOG.md`.

| name | disease | human (original) | claude | match |
|---|---|---|---|---|
| wheat_powdery_mildew_Baidu_0243.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_stripe_rust_Bing_0085.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_leaf_rust_Bing_0028.jpg | wheat leaf rust | close_up | close_up | yes |
| wheat_septoria_blotch_google_septoria (7).jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_leaf_rust_Bing_0014.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_powdery_mildew_Baidu_0003.jpg | wheat powdery mildew | wide | close_up | **no** |
| wheat_leaf_rust_Bing_0016.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_septoria_blotch_Baidu_0010.jpg | wheat septoria blotch | non_photo | close_up | **no** |
| wheat_powdery_mildew_Baidu_0195.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_septoria_blotch_Baidu_0003.jpg | wheat septoria blotch | wide | close_up | **no** |
| wheat_powdery_mildew_Google_0143.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_bacterial_leaf_streak_(black_chaff)_Bing_0024.jpg | wheat bacterial leaf streak (black chaff) | close_up | close_up | yes |
| wheat_powdery_mildew_Baidu_0017.jpg | wheat powdery mildew | wide | wide | yes |
| wheat_powdery_mildew_Baidu_0187.jpg | wheat powdery mildew | non_photo | close_up | **no** |
| wheat_septoria_blotch_blotch (84).jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_leaf_rust_Bing_0030.jpg | wheat leaf rust | wide | non_photo | **no** |
| wheat_stripe_rust_Baidu_0397.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_leaf_rust_Baidu_0112.jpg | wheat leaf rust | non_photo | close_up | **no** |
| wheat_stripe_rust_Google_0085.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_leaf_rust_Baidu_0032.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Baidu_0000.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_septoria_blotch_Baidu_0033.jpg | wheat septoria blotch | wide | close_up | **no** |
| wheat_powdery_mildew_Baidu_0018.jpg | wheat powdery mildew | wide | close_up | **no** |
| wheat_powdery_mildew_Baidu_0186.jpg | wheat powdery mildew | wide | close_up | **no** |
| wheat_powdery_mildew_Bing_0098.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_leaf_rust_Bing_0034.jpg | wheat leaf rust | non_photo | close_up | **no** |
| wheat_leaf_rust_Baidu_0345.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_powdery_mildew_Baidu_0020.jpg | wheat powdery mildew | non_photo | close_up | **no** |
| wheat_leaf_rust_Bing_0009.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Baidu_0072.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Bing_0006.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Bing_0024.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Baidu_0317.jpg | wheat leaf rust | non_photo | close_up | **no** |
| wheat_stripe_rust_Google_0034.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_septoria_blotch_Baidu_0034.jpg | wheat septoria blotch | non_photo | close_up | **no** |
| wheat_septoria_blotch_Baidu_0124.jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_septoria_blotch_blotch (113).jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_leaf_rust_Baidu_0320.jpg | wheat leaf rust | non_photo | close_up | **no** |
| wheat_stripe_rust_Google_0154.jpg | wheat stripe rust | close_up | non_photo | **no** |
| wheat_powdery_mildew_Baidu_0019.jpg | wheat powdery mildew | wide | close_up | **no** |
| wheat_septoria_blotch_blotch (126).jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_leaf_rust_Baidu_0081.jpg | wheat leaf rust | wide | skip | **no** |
| wheat_leaf_rust_Bing_0032.jpg | wheat leaf rust | non_photo | close_up | **no** |
| wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (25).jpg | wheat bacterial leaf streak (black chaff) | close_up | close_up | yes |
| wheat_leaf_rust_Baidu_0263.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Baidu_0080.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_stripe_rust_Bing_0063.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_powdery_mildew_Baidu_0058.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_septoria_blotch_Baidu_0089.jpg | wheat septoria blotch | wide | close_up | **no** |
| wheat_powdery_mildew_Bing_0095.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_powdery_mildew_Google_0014.jpg | wheat powdery mildew | close_up | close_up | yes |
| wheat_bacterial_leaf_streak_(black_chaff)_Google_0363.jpg | wheat bacterial leaf streak (black chaff) | close_up | close_up | yes |
| wheat_bacterial_leaf_streak_(black_chaff)_Baidu_0256.jpg | wheat bacterial leaf streak (black chaff) | close_up | close_up | yes |
| wheat_powdery_mildew_Google_0309.jpg | wheat powdery mildew | close_up | wide | **no** |
| wheat_septoria_blotch_Baidu_0092.jpg | wheat septoria blotch | non_photo | close_up | **no** |
| wheat_leaf_rust_Google_0009.jpg | wheat leaf rust | close_up | close_up | yes |
| wheat_stripe_rust_Baidu_0329.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_septoria_blotch_blotch (55).jpg | wheat septoria blotch | close_up | close_up | yes |
| wheat_powdery_mildew_Baidu_0052.jpg | wheat powdery mildew | close_up | wide | **no** |
| wheat_stripe_rust_Bing_0020.jpg | wheat stripe rust | close_up | close_up | yes |
| wheat_leaf_rust_Google_0235.jpg | wheat leaf rust | close_up | close_up | yes |
| wheat_powdery_mildew_Baidu_0188.jpg | wheat powdery mildew | non_photo | wide | **no** |
| wheat_leaf_rust_Bing_0027.jpg | wheat leaf rust | wide | close_up | **no** |
| wheat_leaf_rust_Baidu_0499.jpg | wheat leaf rust | wide | non_photo | **no** |

## Disagreements (one-line reason each)

| name | disease | human | claude | reason |
|---|---|---|---|---|
| wheat_leaf_rust_Bing_0014.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Baidu_0003.jpg | wheat powdery mildew | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Bing_0016.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_septoria_blotch_Baidu_0010.jpg | wheat septoria blotch | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_septoria_blotch_Baidu_0003.jpg | wheat septoria blotch | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Baidu_0187.jpg | wheat powdery mildew | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Bing_0030.jpg | wheat leaf rust | wide | non_photo | judged non_photo: looked like a multi-panel/labelled comparison image, not a single field photo |
| wheat_leaf_rust_Baidu_0112.jpg | wheat leaf rust | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Baidu_0032.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0000.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_septoria_blotch_Baidu_0033.jpg | wheat septoria blotch | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Baidu_0018.jpg | wheat powdery mildew | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Baidu_0186.jpg | wheat powdery mildew | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Bing_0034.jpg | wheat leaf rust | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Baidu_0345.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Baidu_0020.jpg | wheat powdery mildew | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Bing_0009.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0072.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Bing_0006.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Bing_0024.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0317.jpg | wheat leaf rust | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_septoria_blotch_Baidu_0034.jpg | wheat septoria blotch | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Baidu_0320.jpg | wheat leaf rust | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_stripe_rust_Google_0154.jpg | wheat stripe rust | close_up | non_photo | judged non_photo: looked like a multi-panel/labelled comparison image |
| wheat_powdery_mildew_Baidu_0019.jpg | wheat powdery mildew | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0081.jpg | wheat leaf rust | wide | skip | judged skip: image mainly shows a stem/culm, not leaf tissue |
| wheat_leaf_rust_Bing_0032.jpg | wheat leaf rust | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_leaf_rust_Baidu_0263.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0080.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_septoria_blotch_Baidu_0089.jpg | wheat septoria blotch | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_powdery_mildew_Google_0309.jpg | wheat powdery mildew | close_up | wide | judged wide: leaves appeared small/densely packed, individual leaves hard to distinguish |
| wheat_septoria_blotch_Baidu_0092.jpg | wheat septoria blotch | non_photo | close_up | judged close_up: looked like a real field photo of leaves, not a diagram/banner/collage |
| wheat_powdery_mildew_Baidu_0052.jpg | wheat powdery mildew | close_up | wide | judged wide: leaves appeared small/densely packed, individual leaves hard to distinguish |
| wheat_powdery_mildew_Baidu_0188.jpg | wheat powdery mildew | non_photo | wide | judged wide: looked like a real dense canopy/field photo, not a diagram |
| wheat_leaf_rust_Bing_0027.jpg | wheat leaf rust | wide | close_up | judged close_up: leaves still appeared large/individually distinguishable in frame, not small as wide requires |
| wheat_leaf_rust_Baidu_0499.jpg | wheat leaf rust | wide | non_photo | judged non_photo: looked like a multi-panel/labelled comparison image, not a single field photo |

## Disagreement pattern

- human=wide -> claude=close_up: 19
- human=non_photo -> claude=close_up: 10
- human=wide -> claude=non_photo: 2
- human=close_up -> claude=wide: 2
- human=close_up -> claude=non_photo: 1
- human=wide -> claude=skip: 1
- human=non_photo -> claude=wide: 1
