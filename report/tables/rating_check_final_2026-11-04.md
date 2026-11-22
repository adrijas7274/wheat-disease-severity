# Final rating check: gold finished and locked (2026-11-04)

Source: `data/annotations/rating_log.csv` (rater: adrija), 109 rows. Latest row
per set + image wins. Progress uses the rating tool's own quota logic.

## Counts

| set | disease | done / quota | skipped | left in queue |
|---|---|---|---:|---:|
| tuning | stripe rust | 3 / 3 | 0 | 22 |
| tuning | leaf rust | 3 / 3 | 1 | 2 |
| tuning | powdery mildew | 3 / 3 | 0 | 18 |
| tuning | septoria blotch | 3 / 3 | 0 | 15 |
| tuning | bacterial leaf streak | 3 / 3 | 0 | 8 |
| **gold** | stripe rust | 11 / 11 | 0 | 32 |
| **gold** | leaf rust | 10 / 10 | 0 | 0 |
| **gold** | powdery mildew | 11 / 11 | 13 | 7 |
| **gold** | septoria blotch | 11 / 11 | 11 | 5 |
| **gold** | bacterial leaf streak | 11 / 11 | 8 | 0 |

Tuning: 15 / 15. Gold: 54 / 54, 32 skipped. Recheck: 0 / 15, not started.

Pilot is 4 / 5 by the tool's counter, because the slot reopened by the
`Bing_0016` collage skip was left unrated on purpose (timing only).

## Gold skips

| disease | no single main leaf | main leaf too blurred | not a real photo | total | seen | skip rate |
|---|---:|---:|---:|---:|---:|---:|
| stripe rust | 0 | 0 | 0 | 0 | 11 | 0% |
| leaf rust | 0 | 0 | 0 | 0 | 10 | 0% |
| powdery mildew | 5 | 5 | 3 | 13 | 24 | 54% |
| septoria blotch | 6 | 2 | 3 | 11 | 22 | 50% |
| bacterial leaf streak | 4 | 3 | 1 | 8 | 19 | 42% |
| **all** | **15** | **10** | **7** | **32** | **86** | **37%** |

- The 7 "not a real photo" skips re-tagged 7 **Test** images to `non_photo`. The
  Phase 2 test metrics in `report/tables/baselines.md` predate this, and the
  guidelines require a re-run of that evaluation.
- Bacterial leaf streak used its whole queue and met its quota on the last image.
- 17 skip rows carry click coordinates, 15 of them from the second session. These
  are harmless and ignored for skipped rows.

## Time per image (`rating_s`)

| group | n | median s | mean s | min–max s | under 5 s |
|---|---:|---:|---:|---|---:|
| pilot 3, done | 4 | 12.0 | 14.6 | 11.5–22.9 | 0 |
| tuning, done | 15 | 6.5 | 7.1 | 3.9–11.9 | 4 |
| gold, done | 54 | 5.35 | 6.3 | 3.7–16.6 | 17 |
| gold, skipped | 32 | 6.1 | 11.1 | 3.4–161.1 | 7 |

Gold took 7.7 min of wall clock on 2026-11-02 (52 rows) and 3.7 min on 2026-11-04
(34 rows). The 161 s skip (`powdery_mildew_Google_0014`) looks like a pause.

## Clustering (gold, done)

All 54 values:

3, 3, 3.5, 3.5, 4 (×7), 4.5, 5 (×8), 5.5 (×5), 6, 6.5 (×3), 8.5 (×2), 9 (×2),
9.5 (×6), 11 (×2), 11.5, 12, 16.5 (×2), 19, 20, 31 (×2), 31.5, 34, 34.5, 35.5, 57

| group | n | 4.0–5.5 | 8.5–9.5 | 31–35.5 | in the bands | exactly on a diagram level |
|---|---:|---:|---:|---:|---:|---:|
| all | 54 | 21 | 10 | 6 | 37 (69%) | 9 |
| first 35 | 35 | 14 | 8 | 6 | 28 (80%) | 7 |
| last 19 | 19 | 7 | 2 | 0 | 9 (47%) | 2 |

- Median 6.5%. 46 of 54 are below 20%, and 8 are at 20% or above.
- Nothing below 3.0, nothing strictly between 20 and 31, and nothing above 57.
- 5 values lie between 11 and 20, all from the last 19.

## First 35 vs last 19

| | first 35 (2026-11-02) | last 19 (2026-11-04) |
|---|---:|---:|
| median s | 5.3 | 5.6 |
| mean s | 6.15 | 6.55 |
| min–max s | 3.7–16.6 | 4.4–14.8 |
| under 5 s | 13 (37%) | 4 (21%) |
| median % | 5.5 | 6.5 |
| IQR % | 4.5–10.25 | 5.25–11.25 |
| min–max % | 3–57 | 4–19 |
| SD % | 13.1 | 4.6 |
| values ≥ 20% | 8 | 0 |

**This comparison is confounded.** The first 35 are stripe rust (11), leaf rust
(10), mildew (11) and septoria (3). The last 19 are septoria (8) and bacterial
leaf streak (11). Differences may come from the diseases rather than the rater.
Septoria, the only overlap, is 4, 20, 31 then 4, 4, 4.5, 6.5, 6.5, 9.5, 16.5, 19,
which is too few to conclude from. The rater also saw the tuning leaf rust photos
before the second session, with a comment that 68% might be an overestimate.

| disease | n | median % | range % | median s |
|---|---:|---:|---|---:|
| stripe rust | 11 | 5.0 | 3–31 | 4.5 |
| leaf rust | 10 | 5.25 | 3–34.5 | 5.25 |
| powdery mildew | 11 | 9.5 | 5–57 | 5.6 |
| septoria blotch | 11 | 6.5 | 4–31 | 5.2 |
| bacterial leaf streak | 11 | 6.5 | 5–16.5 | 5.6 |

## Tuning changes

- `Google_0251` (24%) was skipped as a collage. Its replacement, `Google_0000`, was
  rated 7.5% on 2026-11-04.
- Tuning leaf rust is now 68, 20 and 7.5%. `Bing_0046` (68%) was then excluded from
  tuning, with its rating unchanged, so tuning has 14 usable images and 2 for leaf
  rust. The reason is in `experiments/LOG.md` (2026-11-04).

## Integrity checks (all pass)

- Every done gold row has a click and a `rating_s`.
- Every gold row is from the Test split, with one rater.
- No gold image appears in tuning or pilot.
- No gold image has more than one row, so no gold rating was replaced.
- The frozen queue files are unchanged.

## Lock

Gold is locked at git tag `gold-v1`. The rating tool refuses gold saves and skips,
and a test compares the gold rows with `annotation.gold_sha256` in the config.
