# Mask coarseness check: healthy-green fraction inside PlantSeg lesion masks

Approximate, unvalidated HSV heuristic (see experiments/LOG.md 2026-10-03) on close_up-tagged images only. Higher fraction = more of the masked region is still healthy-looking tissue, i.e. the more the raw mask likely overestimates true lesion severity.

| disease | n close_up | n analyzed | mean healthy frac in mask | median |
|---|---|---|---|---|
| wheat stripe rust | 228 | 228 | 62.1% | 65.8% |
| wheat leaf rust | 55 | 55 | 74.1% | 81.4% |
| wheat powdery mildew | 150 | 150 | 74.2% | 81.0% |
| wheat septoria blotch | 136 | 136 | 55.4% | 58.4% |
| wheat bacterial leaf streak (black chaff) | 83 | 83 | 62.0% | 62.8% |
