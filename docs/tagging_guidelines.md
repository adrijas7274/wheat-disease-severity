# Wheat image tagging guidelines

Used when manually tagging PlantSeg v7 wheat leaf-disease images with
`src/data/tag_wheat_images.py` (`data/processed/wheat_tags.csv`). These
definitions are authoritative - the tool's on-screen reminder is a condensed
version of this document, not the other way around.

## Tags

**close_up** - one or a few leaves fill most of the frame, lesions clearly
visible. A cluster of 3-4 leaves still counts.

**wide** - whole plant, group of tillers, or field view, where individual
leaves are small in the frame.

**non_photo** - diagram, drawing, lab plate, collage or multi-panel image, or
banner where text or graphics dominate.

**skip** - doubtful cases: clearly wrong mask, image doesn't seem to show the
stated disease, or mainly shows heads or stems.

## Tie-breaker: close_up vs. wide

If you could draw the outline of the main leaf, it's **close_up**.

## Mask-quality rule (added 2026-10-04)

Check the cyan outline before framing-tagging the image:

- If the outline **follows a leaf's edges**, the mask is good - tag by
  framing as normal (close_up / wide / non_photo).
- If the outline is **just a box around the whole photo or most of it**
  (covering background, stems, or many leaves rather than tracing a lesion),
  the mask is wrong regardless of the framing - tag it **skip**.

Images tagged before this rule existed weren't checked against it. If the
mask covers more than ~90% of the image area, `src/data/list_large_masks.py`
flags it for a recheck - see `report/tables/large_mask_recheck.md` once run.

## Watermarks and text

Small watermarks or text overlays are fine unless they cover the leaf.

## Self-agreement check

After tagging, the tool can re-show you a balanced sample (~20 random
close_up plus every wide/non_photo/skip image) with tags hidden. Re-tag them
from scratch; the tool reports agreement and Cohen's kappa and saves the
result to `report/tables/tagging_agreement.md`. This is an intra-rater
reliability check, not a correctness check - a low agreement rate means the
guidelines above need tightening or a given disease is genuinely ambiguous
to frame, not that either tag was "wrong."

## AI-assisted review pass (2026-10-04) - disclose in report

23 of 706 tags (3.3%) were reviewed and, where warranted, corrected by
Claude rather than by Adrija - specifically the 24 large-mask (>90% area)
wheat powdery mildew images, applying the mask-quality rule above (23
corrected to skip, 1 left unchanged). All 228 stripe rust and 83 bacterial
leaf streak images were also reviewed for the wide/close_up framing rule;
none were changed. `data/processed/wheat_tags.csv` records provenance for
every row (`original_tag` = Adrija's tag, always preserved; `tag` = current
tag; `tag_source` = `human` or `claude_review`; `review_reason` for AI
changes), so this is fully auditable.

A second-rater check (Claude independently re-tagging a blind balanced
sample of 64 images, human tags hidden) found **28/64 (43.8%) agreement,
Cohen's kappa -0.006** with Adrija's original tags - essentially
chance-level, concentrated almost entirely on the wide and non_photo
categories (Claude applied a visibly stricter threshold for both than
Adrija did). Full results: `report/tables/inter_rater_agreement.md`. This
should be stated honestly in the report as a real limitation of the current
close_up/wide/non_photo boundary, not smoothed over - see
`experiments/LOG.md` (2026-10-04 entry) for the full discussion.
