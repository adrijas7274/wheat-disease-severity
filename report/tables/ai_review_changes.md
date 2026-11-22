# AI-assisted tag review changes

23 images changed by Claude during the 2026-10-04 tag review pass,
out of 706 total. Every change is recorded in data/processed/wheat_tags.csv
with tag_source=claude_review; original_tag preserves the human's original tag
unchanged. See docs/tagging_guidelines.md and experiments/LOG.md for the rules applied.

| name | disease | human tag (original_tag) | new tag | reason |
|---|---|---|---|---|
| wheat_powdery_mildew_Baidu_0003.jpg | wheat powdery mildew | wide | skip | mask covers whole canopy, many leaves plus background |
| wheat_powdery_mildew_Baidu_0006.jpg | wheat powdery mildew | close_up | skip | mask covers many overlapping leaves |
| wheat_powdery_mildew_Baidu_0017.jpg | wheat powdery mildew | wide | skip | mask covers a head/spike cluster plus background |
| wheat_powdery_mildew_Baidu_0024.jpg | wheat powdery mildew | close_up | skip | mask covers multiple overlapping leaf blades |
| wheat_powdery_mildew_Baidu_0035.jpg | wheat powdery mildew | close_up | skip | mask covers whole canopy cluster |
| wheat_powdery_mildew_Baidu_0049.jpg | wheat powdery mildew | close_up | skip | mask covers whole canopy, no leaf-specific boundary |
| wheat_powdery_mildew_Baidu_0052.jpg | wheat powdery mildew | close_up | skip | mask covers leaves plus visible soil background |
| wheat_powdery_mildew_Baidu_0085.jpg | wheat powdery mildew | close_up | skip | mask covers many overlapping leaves |
| wheat_powdery_mildew_Baidu_0102.jpg | wheat powdery mildew | close_up | skip | mask covers a cluster of overlapping leaves |
| wheat_powdery_mildew_Baidu_0169.jpg | wheat powdery mildew | close_up | skip | mask traces a wheat spike/stem structure, not a leaf |
| wheat_powdery_mildew_Baidu_0181.jpg | wheat powdery mildew | close_up | skip | mask spans many leaf blades across a wide irregular area |
| wheat_powdery_mildew_Baidu_0188.jpg | wheat powdery mildew | non_photo | skip | mask covers whole canopy incl. soil background; also looks like a real photo, not non_photo |
| wheat_powdery_mildew_Baidu_0189.jpg | wheat powdery mildew | close_up | skip | image is a multi-panel composite with labelled sub-regions, not a single clean photo |
| wheat_powdery_mildew_Baidu_0190.jpg | wheat powdery mildew | close_up | skip | mask covers many overlapping leaves |
| wheat_powdery_mildew_Baidu_0199.jpg | wheat powdery mildew | close_up | skip | image is two stacked photo panels (collage), not a single photo |
| wheat_powdery_mildew_Baidu_0204.jpg | wheat powdery mildew | close_up | skip | mask covers leaves plus dark soil background |
| wheat_powdery_mildew_Baidu_0208.jpg | wheat powdery mildew | close_up | skip | mask covers many parallel leaf blades |
| wheat_powdery_mildew_Baidu_0272.jpg | wheat powdery mildew | close_up | skip | mask covers a mini wheat-field view including heads, not one leaf |
| wheat_powdery_mildew_Baidu_0286.jpg | wheat powdery mildew | close_up | skip | mask covers many overlapping leaves, not one leaf |
| wheat_powdery_mildew_Bing_0010.jpg | wheat powdery mildew | close_up | skip | mask covers leaves plus visible soil background |
| wheat_powdery_mildew_Bing_0074.jpg | wheat powdery mildew | close_up | skip | mask covers many overlapping leaves |
| wheat_powdery_mildew_Google_0093.jpg | wheat powdery mildew | close_up | skip | mask covers a whole crop-row view, many plants plus background |
| wheat_powdery_mildew_Google_0309.jpg | wheat powdery mildew | close_up | skip | mask covers ~100% of frame, no leaf-specific boundary, many overlapping leaves |
