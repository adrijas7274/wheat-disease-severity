# Mobile version (final-v1-mobile): parity with the Python pipelines

Clean test split, 121 close-up images, the final-v1 automatic click as the tap. Commit `ec2c12131edac00303649dadaa896e44500d79a8`. Nothing in the mobile version was chosen or tuned on these images. Levels and decisions are PLACEHOLDERS.

- **final-v1**: Python, PyTorch SegFormer-B0 + SAM 2.1 tiny (the frozen pipeline).
- **mobile (Python)**: same code, SegFormer-B0 INT8 + EfficientSAM-Ti INT8 (ONNX).
- **mobile (browser)**: the JavaScript port (`app/web/js/pipeline.js`) with onnxruntime-web 1.20.1 (WebAssembly, 1 thread), run in Node.

## Agreement

| comparison | images with a severity in both | severity difference, points: mean / median / 95th pct / max | within 1 point | same level | same decision | same gate result | same action (answer / consult / retake) |
|---|---:|---|---:|---:|---:|---:|---:|
| **mobile (browser) vs final-v1**: the mobile version's numbers | 121 | 2.23 / 0.11 / 9.3 / 35.8 | 74% | 88% | 88% | 100% | 93% |
| mobile (Python) vs final-v1: effect of the phone models | 121 | 2.16 / 0.09 / 9.2 / 35.7 | 74% | 88% | 88% | 100% | 93% |
| mobile (browser) vs mobile (Python): porting error | 121 | 0.15 / 0.01 / 0.6 / 3.1 | 96% | 100% | 100% | 100% | 99% |

## What each pipeline answers

| pipeline | answer | consult an expert | retake |
|---|---:|---:|---:|
| final-v1 | 70% | 22% | 7% |
| mobile (Python) | 71% | 21% | 7% |
| mobile (browser) | 70% | 22% | 7% |

## Masks

| masks | median IoU | lowest IoU | images below 0.9 |
|---|---:|---:|---:|
| region js vs py | 0.992 | 0.931 | 0 |
| leaf js vs py | 0.996 | 0.822 | 1 |
| leaf mobile vs final | 0.941 | 0.016 | 54 |

Gate features, largest relative difference browser vs Python: sharpness 3.0e-04, noise 1.0e-02, luma 1.7e-04, clip_high 1.7e-04, clip_low 0.0e+00, blockiness 1.9e-05, min_side 0.0e+00.

## Speed of the browser pipeline (Node, WebAssembly, 1 thread, laptop CPU; median ms per photo)

| gate | region | leaf encoder | leaf decoder | colour rule + uncertainty | total |
|---:|---:|---:|---:|---:|---:|
| 35 | 532 | 5831 | 155 | 30 | 6625 |

Phone speed is measured separately (fallback rule: more than 10 s per photo -> MobileSAM INT8).
