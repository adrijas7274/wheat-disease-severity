# Gold level and decision agreement with the corrected level mapping (2026-11-14)

Re-binned from the single gold run `experiments/20261114_174642_gold_evaluation`; no image was scored again and the MAE values are unchanged (`report/tables/gold_evaluation.md`).

**PLACEHOLDER levels and mapping** (not validated against an agronomy source): none = 0%, low below 5%, medium below 20%, high above; decisions {'none': 'no_action', 'low': 'monitor', 'medium': 'treat', 'high': 'treat_urgently'}. A rating within 3.64 points of a threshold (the resolution limit) can change level from rating noise alone.

## All 37 images

| method | same level | same decision |
|---|---:|---:|
| A | 22% | 22% |
| B | 22% | 22% |
| C(A) | 22% | 22% |
| C(B) | 22% | 22% |

Level confusion (rating level -> method level: count):

- A: high -> high: 6; low -> high: 7; low -> medium: 1; medium -> high: 21; medium -> medium: 2
- B: high -> high: 6; low -> high: 7; low -> medium: 1; medium -> high: 20; medium -> low: 1; medium -> medium: 2
- C(A): high -> high: 1; high -> low: 3; high -> medium: 1; high -> none: 1; low -> high: 4; low -> low: 1; low -> medium: 2; low -> none: 1; medium -> high: 4; medium -> low: 9; medium -> medium: 6; medium -> none: 4
- C(B): high -> high: 1; high -> low: 2; high -> medium: 1; high -> none: 2; low -> high: 4; low -> low: 1; low -> medium: 2; low -> none: 1; medium -> high: 4; medium -> low: 9; medium -> medium: 6; medium -> none: 4

## Without `wheat_bacterial_leaf_streak_(black_chaff)_black_chaff (25).jpg` (36 images)

| method | same level | same decision |
|---|---:|---:|
| A | 22% | 22% |
| B | 22% | 22% |
| C(A) | 19% | 19% |
| C(B) | 19% | 19% |

Level confusion (rating level -> method level: count):

- A: high -> high: 6; low -> high: 7; low -> medium: 1; medium -> high: 20; medium -> medium: 2
- B: high -> high: 6; low -> high: 7; low -> medium: 1; medium -> high: 19; medium -> low: 1; medium -> medium: 2
- C(A): high -> high: 1; high -> low: 3; high -> medium: 1; high -> none: 1; low -> high: 4; low -> low: 1; low -> medium: 2; low -> none: 1; medium -> high: 4; medium -> low: 9; medium -> medium: 5; medium -> none: 4
- C(B): high -> high: 1; high -> low: 2; high -> medium: 1; high -> none: 2; low -> high: 4; low -> low: 1; low -> medium: 2; low -> none: 1; medium -> high: 4; medium -> low: 9; medium -> medium: 5; medium -> none: 4
