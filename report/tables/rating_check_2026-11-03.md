# Rating check: tuning + gold (2026-11-03)

Source: `data/annotations/rating_log.csv` (rater: adrija). It is identical to
`backups/rating_log_2026-11-02_after_gold_session1.csv`. All ratings were
saved on 2026-11-02 between 11:01 and 11:10 UTC. Progress was computed with
the rating tool's own quota logic (`annotation_core.progress`), so "done"
here means the same as the tool's counter.

## Status: tuning finished, gold NOT finished

| set | disease | done / quota | skipped | left in queue |
|---|---|---|---|---|
| tuning | stripe rust | 3 / 3 | 0 | 22 |
| tuning | leaf rust | 3 / 3 | 0 | 3 |
| tuning | powdery mildew | 3 / 3 | 0 | 18 |
| tuning | septoria blotch | 3 / 3 | 0 | 15 |
| tuning | bacterial leaf streak | 3 / 3 | 0 | 8 |
| **gold** | stripe rust | 11 / 11 | 0 | 32 |
| **gold** | leaf rust | 10 / 10 | 0 | 0 |
| **gold** | powdery mildew | 11 / 11 | **13** | 7 |
| **gold** | septoria blotch | **3 / 11** | 4 | 20 |
| **gold** | bacterial leaf streak | **0 / 11** | 0 | 19 |

Gold: **35 / 54 rated**, 17 skipped. 19 ratings are still missing (8 septoria
and 11 bacterial leaf streak). The blind recheck (15 images) can't start
until gold is finished.

## Skips (gold only; tuning had none)

| disease | reason | n |
|---|---|---|
| powdery mildew | main leaf too blurred | 5 |
| powdery mildew | no single main leaf | 5 |
| powdery mildew | not a real photo (mis-tagged) | 3 |
| septoria blotch | no single main leaf | 2 |
| septoria blotch | not a real photo (mis-tagged) | 2 |

- Mildew: 13 of 24 seen were skipped (54%). Only 7 remain in the queue, so
  if the quota had not already been met, mildew could have run out.
- Septoria: so far 4 of 7 seen were skipped. With 20 left in the queue,
  running out is unlikely.
- The 5 "not a real photo" skips re-tagged 5 **Test** images to `non_photo`
  in `data/processed/wheat_tags.csv`. The Phase 2 test metrics in
  `report/tables/baselines.md` were computed before this and still include
  them.
- 2 skip rows carry click coordinates (`powdery_mildew_Bing_0054`,
  `septoria google_septoria (18)`). They are harmless (a click before
  deciding to skip) and are ignored for skipped rows.

## Time per image (`rating_s`)

| set | rows | median s | mean s | min–max s | wall clock |
|---|---|---|---|---|---|
| pilot 3 (for reference) | 5 | 12.5 | 30.2 | 11.5–92.8 | — |
| tuning | 15 | 5.9 | 6.8 | 3.9–11.9 | 1.5 min |
| gold | 52 | 5.2 | 9.0 | 3.4–161.1 | 7.7 min |

- Gold ratings (done only): median 5.3 s, and 13 of 35 took under 5 s.
- The 161 s outlier is a skip (`powdery_mildew_Google_0014`, "no single
  main leaf"). It looks like a pause or deliberation, not rating time.
- The median gap between consecutive saves is 5.0 s, so `rating_s` isn't
  hiding extra time spent elsewhere.

## Rating distribution (gold, done)

Values: 3.0 to 57.0%, median 5.5%. Values cluster near the reference-diagram
levels (1, 2, 5, 10, 20, 35, 50, 75): 14 values are in 4.0–5.5, 8 are in
8.5–9.5, and 6 are in 31–35.5. There are no values between 11 and 20. One
value is exactly 20.0, and none are between 20 and 31.

*Corrected 2026-11-04: this paragraph first said 11, 7 and 5 values, and
"only one between 20 and 31". Those counts were wrong; the values above were
recomputed from the log. No ratings changed.*

Per disease (median, range): stripe rust 5.0 (3–31), leaf rust 5.2
(3–34.5), mildew 9.5 (5–57), septoria 20.0 (4–31, n=3).

Tuning leaf rust (68, 24, 20%) is much higher than gold leaf rust (median
5.2%). This could be real image differences, or the same rust
overestimation the training sessions showed. Tuning has only 3 images, so
this is a flag to look at, not a conclusion.

## Rater training before rating (`report/tables/rater_training.md`)

| session (UTC) | MAE (pp) | signed (pp) |
|---|---|---|
| 08:57 | 20.27 | — |
| 09:00 | 20.43 | +20.30 (rust +35.8) |
| 09:03 | 4.60 | −1.60 |

Only the third session reached a low error. No training was done between
09:03 and the gold ratings (11:01).

## Integrity checks (all pass)

- No duplicate names within tuning or gold.
- Every split matches its set (tuning=Validation, gold=Test).
- Every done row has a click and a `rating_s`.
- No gold image appears in tuning or pilot.
