"""Gradio demo of the frozen final-v1 pipeline: upload a wheat leaf photo, choose the disease, tap the main leaf.

Run locally (from the repository root):   python demo/app.py
On Hugging Face Spaces this file is the Space's app.py (see demo/DEPLOY.md).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent if (Path(__file__).resolve().parent.parent / "src").exists() else Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import cv2  # noqa: E402
import gradio as gr  # noqa: E402
import numpy as np  # noqa: E402

from src.demo.pipeline import DISEASES, Pipeline  # noqa: E402
from src.demo.space_setup import ensure_checkpoints  # noqa: E402

EXAMPLES_DIR = Path("demo/examples")
TITLE = "Wheat leaf disease severity, with a 'retake' and 'consult an expert' check"
DISCLAIMER = """
> **Decision support, not expert advice.** This is a final-year student research prototype. The severity
> levels (0%, 5%, 20%) and the recommendations are **placeholders that have not been validated** against an
> agronomy source. Always confirm with an agriculture expert before spraying.
"""
HOW_TO = """
**How to use:** 1) upload a photo of one wheat leaf (or pick an example below), 2) choose the disease you suspect,
3) **tap the middle of the main leaf** in the photo. The result appears on the right.
"""
LIMITATIONS = """
### Known limitations
- **Powdery mildew false alarms:** on healthy leaves the mildew colour rule often reports some severity
  (above 0% on 36-63% of healthy leaves in two external field sets).
- **Colour casts** (yellow or blue tint, odd white balance) move the estimate a lot, and the photo check
  catches only a few of them.
- **Septoria** is the weakest disease: on an independent field set only 58% of septoria photos got a
  severity above 0%.
- It measures the share of the leaf inside the predicted infected region that has the disease's colour.
  The training masks are coarse, so this is an approximation, checked against one rater (mean error about
  14 points on clean photos).
- You choose the disease: the demo does not diagnose it. Wheat leaf diseases only (stripe rust, leaf rust,
  powdery mildew, septoria, bacterial leaf streak).
"""
CREDITS = """
### Credits and licences
- Infected-region model trained on **PlantSeg** (Wei et al., 2024, arXiv:2409.04038; Zenodo record 17719108,
  **CC BY-NC 4.0**), so the model and this demo are for **non-commercial** use only.
- Leaf masks: **SAM 2.1 hiera-tiny** (Meta, Apache 2.0).
- Example photos: **JIC wheat disease images**, Long, Hartley, Morris & Brown (2023), Zenodo 7573133,
  **CC BY 4.0**, resized.
- External test sets: Mendeley Wheat Leaf Dataset (Getachew, 2021, CC BY 4.0), JIC (above); healthy guard
  set: Radowan & Ayon (2025), Mendeley 5gc7hwydwg, CC BY 4.0.
"""
BLURRED_PREFIX = "z_blurred_"  # sorts last; shown in its own example block
ACTION_LABEL = {"answer": "Answer given", "retake": "Please retake the photo", "consult": "Consult an expert"}


def overlay(image: np.ndarray, leaf: np.ndarray | None, lesion: np.ndarray | None, click: tuple[int, int] | None) -> np.ndarray:
    """Lesion pixels in red over the photo, leaf outline in yellow, tap as a cyan dot."""
    out = image.copy()
    if lesion is not None and lesion.any():
        out[lesion] = (0.45 * out[lesion] + 0.55 * np.array([230, 30, 30])).astype(np.uint8)
    width = max(2, round(max(image.shape[:2]) / 400))
    if leaf is not None and leaf.any():
        contours, _ = cv2.findContours(leaf.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(out, contours, -1, (255, 220, 0), width)
    if click is not None:
        cv2.circle(out, click, 3 * width, (0, 230, 255), -1)
    return out


def build_app(pipeline: Pipeline) -> gr.Blocks:
    def on_upload(image):
        return image, None, "Now choose the disease and **tap the middle of the main leaf** in the photo."

    def on_tap(original, disease, evt: gr.SelectData):
        if original is None:
            return None, "Upload a photo first."
        click = (int(evt.index[0]), int(evt.index[1]))
        res = pipeline.analyse(original, disease, click)
        scale = res.image.shape[0] / original.shape[0]
        shown = overlay(res.image, res.leaf, res.lesion if res.action != "retake" else None,
                        (round(click[0] * scale), round(click[1] * scale)))
        lines = [f"## {ACTION_LABEL[res.action]}", "", res.reason, ""]
        if res.severity is not None:
            lines.append(f"- Severity (lesion area / leaf area): **{res.severity:.1f}%**, level **{res.level}** (placeholder)")
        lines.append(f"- Photo check: {'passed' if not res.failed_checks else 'failed (' + ', '.join(res.failed_checks) + ')'}")
        lines.append(f"- Uncertainty (spread under small brightness and colour changes): {res.uncertainty:.1f} points; "
                     f"'consult an expert' above {res.uncertainty_threshold:.1f}")
        lines.append("")
        lines.append("Yellow line: the leaf found from your tap. Red: pixels counted as diseased.")
        return shown, "\n".join(lines)

    with gr.Blocks(title="Wheat severity demo") as app:
        gr.Markdown(f"# {TITLE}")
        gr.Markdown(DISCLAIMER)
        gr.Markdown(HOW_TO)
        original = gr.State(None)
        with gr.Row():
            with gr.Column():
                photo = gr.Image(type="numpy", label="Your photo: tap the main leaf", sources=["upload", "clipboard"], height=420)
                disease = gr.Dropdown(DISEASES, value=DISEASES[0], label="Disease you suspect")
            with gr.Column():
                result_image = gr.Image(type="numpy", label="Leaf outline and lesions", interactive=False, height=420)
                result_text = gr.Markdown("Upload a photo to start.")
        examples = sorted(EXAMPLES_DIR.glob("*.jpg"))
        normal = [p for p in examples if not p.name.startswith(BLURRED_PREFIX)]
        blurred = [p for p in examples if p.name.startswith(BLURRED_PREFIX)]
        if normal:
            gr.Examples([[str(p), _disease_of(p.name)] for p in normal], inputs=[photo, disease],
                        label="Example photos (then tap the leaf)")
        if blurred:
            gr.Examples([[str(p), _disease_of(p.name)] for p in blurred], inputs=[photo, disease],
                        label="Blurred photo (shows retake)")
        photo.upload(on_upload, photo, [original, result_image, result_text])
        photo.change(lambda im: im, photo, original)
        photo.select(on_tap, [original, disease], [result_image, result_text])
        gr.Markdown(LIMITATIONS)
        gr.Markdown(CREDITS)
    return app


def _disease_of(filename: str) -> str:
    """Example files are named <disease key>_<n>.jpg, or z_blurred_<disease key>_<n>.jpg for the retake example."""
    key = filename.removeprefix(BLURRED_PREFIX).rsplit("_", 1)[0].replace("_", " ")
    return next((d for d in DISEASES if d.startswith(key)), DISEASES[0])


if __name__ == "__main__":
    ensure_checkpoints()
    # GRADIO_SHARE=1 gives a temporary public *.gradio.live link (used by the Colab notebook)
    build_app(Pipeline(device="cpu")).launch(server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
                                             share=os.environ.get("GRADIO_SHARE") == "1")
