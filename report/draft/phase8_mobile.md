# Phase 8 — Mobile version (draft; phone results pending)

## Methods

**Mobile version `final-v1-mobile`.** The frozen final-v1 pipeline with two models swapped for phone-sized ones:
the SegFormer-B0 region model exported to ONNX with dynamic INT8 quantisation (7.8 MB), and the leaf finder
EfficientSAM-Ti with INT8 encoder and decoder (17.8 MB), in place of SAM 2.1 tiny. Every rule is unchanged: the
`min_area` leaf choice (min share 0.02), the C1 colour rule, the Phase 6 v2 quality gate, the photometric-spread
consult threshold (3.0432) and the placeholder levels and decisions.

**Leaf finder choice.** Three phone options were compared with the frozen SAM 2 leaf on the 78 tuning images only
(no gold, no test): MobileSAM INT8, EfficientSAM-Ti INT8 and a tap-and-box GrabCut
(`report/tables/leaf_finders.md`). EfficientSAM-Ti INT8 gave the same placeholder level on 94% of the images
(12/12 on the rated subset), against 88% for MobileSAM and 74% for GrabCut, and was the smallest file. Adrija chose
it, with a fallback fixed before any phone measurement: if the app takes more than 10 s of compute per photo on the
test phone, switch to MobileSAM INT8.

**On-device pipeline.** The whole pipeline is ported to JavaScript (`app/web/js/pipeline.js`) and runs the ONNX
models with onnxruntime-web (WebAssembly). OpenCV operations that change results are reproduced exactly: the
INTER_AREA tables, fixed-point grey and HSV conversion, and 11-bit bilinear resizing. The pipeline runs in two
stages, so the slow leaf encoder runs while the farmer picks the disease and taps.

**Parity test.** The JavaScript pipeline (run in Node), the Python mobile pipeline and final-v1 were run on the
121 clean test images, with the final-v1 automatic click as the tap. Nothing in the mobile version was chosen or
tuned on these images.

**App.** An offline progressive web app hosted on GitHub Pages and packaged as an Android APK with Capacitor 6.
The flow is: photo, then disease, then a tap on the leaf, then a result card. Each of the six outcomes has its own
colour and icon: no action, monitor, treat, treat urgently, retake, and consult an expert.
- Languages: the 22 scheduled Indian languages plus English, each with a self-hosted Noto font loaded on demand.
- Read-aloud: the phone's text-to-speech reads each result.
- Translations: every non-English translation is a machine draft, flagged in the app, until a native speaker
  checks it.

## Results

| comparison (121 test images) | severity diff, mean / median / max (points) | same level | same decision | same gate | same action |
|---|---|---:|---:|---:|---:|
| mobile (browser) vs final-v1 | 2.23 / 0.11 / 35.8 | 88% | 88% | 100% | 93% |
| mobile (Python) vs final-v1 | 2.16 / 0.09 / 35.7 | 88% | 88% | 100% | 93% |
| mobile (browser) vs mobile (Python) | 0.15 / 0.01 / 3.1 | 100% | 100% | 100% | 99% |

- Almost all of the difference from final-v1 comes from the phone leaf finder, not from the JavaScript port. The
  leaf IoU against SAM 2 has a median of 0.94, and 54 images are below 0.9.
- The share of answer, consult and retake outcomes is unchanged: 70 / 22 / 7%.
- Speed on the laptop CPU: 6.6 s per photo with 1 WebAssembly thread (Node). With 4 threads in Chromium at phone
  screen size it was 3.1 s.
- Phone speed and memory: **TODO (phone test)**.
- App size: 37.2 MB cached for offline use, plus 1.04 MB of script fonts downloaded on demand. The APK is 29.1 MB.

## Limitations

- The mobile version is not final-v1: 12% of the test images change placeholder level, mainly because the leaf
  finder picks a different or partial leaf.
- The levels and advice are placeholders that have not been checked against an agronomy source.
- No translation has been checked by a native speaker. The Santali, Manipuri (Meetei Mayek) and Bodo drafts are
  the least reliable.
- Offline text-to-speech depends on the voices installed on each phone. Many Indian languages have no voice.
- The APK is debug-signed and meant for testing only.
