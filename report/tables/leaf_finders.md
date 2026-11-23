# Phase 8 step 1: phone-sized leaf finders vs the frozen SAM 2 tiny rule (tuning images only)

Run `experiments/20261123_125054_leaf_finders`, commit `ec2c12131edac00303649dadaa896e44500d79a8`. Reference = SAM 2.1 tiny + the frozen `min_area` rule (final-v1), **not ground truth**. Every SAM-style finder uses the same frozen rule on its 3 candidates. Severity uses the same SegFormer-B0 region and colour rule (no preprocessing), so only the leaf changes. No gold image was opened.

## Agreement with the SAM 2 leaf

### Rated tuning images, Adrija's clicks (n = 12)

| finder | leaf IoU, median | IoU < 0.5 | severity diff, mean / median / max (points) | same level | MAE vs rating |
|---|---:|---:|---|---:|---:|
| mobile_sam | 0.93 | 1 | 4.0 / 0.1 / 37.9 | 92% | 17.2 |
| mobile_sam_int8 | 0.93 | 1 | 4.4 / 0.1 / 37.7 | 92% | 16.9 |
| efficient_sam | 0.93 | 1 | 1.6 / 0.1 / 13.1 | 100% | 15.8 |
| efficient_sam_int8 | 0.92 | 1 | 1.4 / 0.1 / 11.5 | 100% | 15.7 |
| grabcut | 0.68 | 5 | 11.3 / 2.3 / 44.9 | 75% | 11.4 |
| *sam2_tiny (reference)* | 1.00 | 0 | 0 | 100% | 15.1 |

### Other tuning-queue images, automatic click (n = 66)

| finder | leaf IoU, median | IoU < 0.5 | severity diff, mean / median / max (points) | same level | MAE vs rating |
|---|---:|---:|---|---:|---:|
| mobile_sam | 0.97 | 7 | 1.0 / 0.1 / 20.1 | 89% | – |
| mobile_sam_int8 | 0.97 | 7 | 1.1 / 0.1 / 20.1 | 88% | – |
| efficient_sam | 0.96 | 6 | 1.2 / 0.1 / 20.0 | 94% | – |
| efficient_sam_int8 | 0.97 | 6 | 1.2 / 0.1 / 20.0 | 92% | – |
| grabcut | 0.52 | 32 | 5.6 / 0.9 / 66.5 | 74% | – |

### All (n = 78)

| finder | leaf IoU, median | IoU < 0.5 | severity diff, mean / median / max (points) | same level | MAE vs rating |
|---|---:|---:|---|---:|---:|
| mobile_sam | 0.97 | 8 | 1.5 / 0.1 / 37.9 | 90% | – |
| mobile_sam_int8 | 0.97 | 8 | 1.6 / 0.1 / 37.7 | 88% | – |
| efficient_sam | 0.96 | 7 | 1.2 / 0.1 / 20.0 | 95% | – |
| efficient_sam_int8 | 0.96 | 7 | 1.2 / 0.1 / 20.0 | 94% | – |
| grabcut | 0.54 | 37 | 6.5 / 1.0 / 66.5 | 74% | – |

## Size and speed (laptop CPU, onnxruntime; SAM 2 tiny in PyTorch; photo long side 1024 px)

| finder | files | 1 thread: encoder + decoder (ms) | 4 threads: encoder + decoder (ms) |
|---|---:|---:|---:|
| sam2_tiny | 156 MB (PyTorch) | 3714 + 151 | 1085 + 48 |
| mobile_sam | 44.4 MB | 3129 + 219 | 437 + 34 |
| mobile_sam_int8 | 26.9 MB | 1622 + 81 | 366 + 29 |
| efficient_sam | 41.4 MB | 2847 + 80 | 924 + 32 |
| efficient_sam_int8 | 17.8 MB | 2160 + 54 | 822 + 30 |
| grabcut | 0 (OpenCV; OpenCV.js ~9 MB in a browser) | 0 + 1320 | – |

Times are medians on this laptop's CPU, not a phone; in a browser (onnxruntime-web, WebAssembly) expect them to be several times slower. GrabCut runs at 512 px with OpenCV (1 thread).

Contact sheets: `report/figures/leaf_finders/rated.png` (all rated images) and `report/figures/leaf_finders/queue_worst.png` (the 12 queue images with the lowest MobileSAM INT8 IoU).
