"""Keyboard-driven manual tagging tool for the wheat leaf-disease images.

Shows each image plain (original) next to a copy with the lesion mask drawn
as a cyan outline (not filled, so the leaf itself stays visible), and lets
you tag it as close_up, wide, non_photo, or skip using number keys (1-4) or
the on-screen buttons. Every tag is written to disk immediately, so you can
close the window at any time and resume later from the first untagged image.

Memory: only the current image+mask pair is ever decoded. Large source
JPEGs are decoded directly at a reduced size via PIL's draft() mode rather
than decoded full-size and then downscaled.

Full tagging rules: docs/tagging_guidelines.md (this tool only shows a
condensed on-screen reminder).

Usage:
    .venv\\Scripts\\python.exe -m src.data.tag_wheat_images --config configs/config.yaml

Keys (Tag tab): 1=close_up  2=wide  3=non_photo  4=skip  Backspace=undo last  q=quit
Keys (Self-check tab): 1=close_up  2=wide  3=non_photo  4=skip
Keys (Review tab): 1=close_up  2=wide  3=non_photo  4=skip (re-tag and advance)
                   Right arrow=next (keep tag)  Left arrow=previous
"""

import argparse
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
from PIL import Image, ImageChops, ImageFilter

OUTLINE_COLOR = (0, 255, 255)  # cyan

from src.data.list_large_masks import DEFAULT_THRESHOLD, find_large_mask_tagged_images
from src.data.wheat_metadata import (
    filter_by_crop_and_disease, image_path, load_metadata_rows, mask_path,
)
from src.data.wheat_self_check import sample_balanced_tagged_rows, write_agreement_report
from src.data.wheat_tags import append_tag, load_tags, next_untagged_index, remove_last_tag
from src.utils.config import load_config

RULES_REMINDER = """
**close_up**: 1-few leaves fill most of the frame, lesions visible (3-4 leaves still counts) &nbsp;|&nbsp;
**wide**: whole plant / tillers / field, leaves small in frame &nbsp;|&nbsp;
**non_photo**: diagram, lab plate, collage, banner &nbsp;|&nbsp;
**skip**: wrong mask, wrong disease, mostly heads/stems, **or outline is a box over most of the photo (not tracing a leaf)** &nbsp;|&nbsp;
**tie-break**: if you could outline the main leaf → close_up &nbsp;|&nbsp;
small watermarks/text are fine unless they cover the leaf.
Full rules: `docs/tagging_guidelines.md`.
"""

KEY_JS = """
function() {
  document.addEventListener('keydown', function(e) {
    // Never hijack keystrokes while the user is typing in a text field (e.g.
    // filtering a searchable Dropdown) - a stray Backspace here previously
    // triggered "Undo" and silently deleted tag rows. See experiments/LOG.md.
    const t = e.target;
    const tag = (t.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || t.isContentEditable) return;

    const pairs = {
      '1': ['tag-btn-close-up', 'sc-btn-close-up', 'rv-btn-close-up'],
      '2': ['tag-btn-wide', 'sc-btn-wide', 'rv-btn-wide'],
      '3': ['tag-btn-non-photo', 'sc-btn-non-photo', 'rv-btn-non-photo'],
      '4': ['tag-btn-skip', 'sc-btn-skip', 'rv-btn-skip'],
      'Backspace': ['tag-btn-undo'],
      'q': ['tag-btn-quit'],
      'ArrowRight': ['rv-btn-next'],
      'ArrowLeft': ['rv-btn-prev'],
    };
    const ids = pairs[e.key];
    if (!ids) return;
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el && el.offsetParent !== null) { el.click(); e.preventDefault(); break; }
    }
  });
}
"""


def load_ordered_rows(config: dict) -> list[dict]:
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    rows = load_metadata_rows(plantseg_dir / "Metadata.csv")
    rows = filter_by_crop_and_disease(rows, config["crop"], config["disease_classes"])
    rows.sort(key=lambda r: r["name"])  # deterministic order across runs
    return rows


def rows_for_disease(config: dict, disease: str) -> list[dict]:
    return [r for r in load_ordered_rows(config) if r["disease"] == disease]


def tags_csv_path(config: dict) -> Path:
    return Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"


def tagged_rows_for_disease(config: dict, disease: str) -> list[dict]:
    """All already-tagged rows for one disease class, each with a "tag" field."""
    tags = load_tags(tags_csv_path(config))
    rows = [dict(r, tag=tags[r["name"]]) for r in rows_for_disease(config, disease) if r["name"] in tags]
    rows.sort(key=lambda r: r["name"])
    return rows


def large_mask_review_rows(config: dict, disease: str, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    """Full metadata rows (for image/mask paths) for the large-mask recheck
    list, filtered to one disease, sorted by mask area descending.
    """
    flagged = [r for r in find_large_mask_tagged_images(config, threshold=threshold) if r["disease"] == disease]
    by_name = {r["name"]: r for r in load_ordered_rows(config)}
    return [dict(by_name[r["name"]], tag=r["tag"], mask_area_fraction=r["mask_area_fraction"]) for r in flagged]


# Review tab's list choices -> a function building that list's rows from config.
REVIEW_LISTS: dict[str, "callable"] = {
    "Large-mask (>90%) wheat powdery mildew": lambda config: large_mask_review_rows(config, "wheat powdery mildew"),
    "All wheat stripe rust": lambda config: tagged_rows_for_disease(config, "wheat stripe rust"),
    "All wheat bacterial leaf streak": lambda config: tagged_rows_for_disease(
        config, "wheat bacterial leaf streak (black chaff)"
    ),
}


def review_status(row: dict, idx: int, total: int, list_name: str) -> str:
    status = f"{idx + 1}/{total} — {list_name} — current tag: {row['tag']} — {row['disease']} — {row['name']}"
    if "mask_area_fraction" in row:
        status += f" — mask area {row['mask_area_fraction']:.1%}"
    return status


def load_resized_image(img_path: Path, max_dim: int = 700) -> Image.Image:
    img = Image.open(img_path)
    # PlantSeg images go up to 6000x5408px (~97MB once decoded to raw RGB).
    # draft() asks the JPEG decoder to decode at a reduced size directly
    # (DCT scaling), so we never materialize the full-resolution buffer just
    # to immediately downscale it. No-op for non-JPEG files or if already small.
    img.draft("RGB", (max_dim, max_dim))
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    return img


def mask_outline(mask_path_: Path, size: tuple[int, int], thickness: int = 5) -> Image.Image:
    """L-mode image, 255 on a ~thickness-px band around the lesion boundary, 0 elsewhere."""
    mask = Image.open(mask_path_).convert("L").resize(size, Image.NEAREST)
    mask_binary = mask.point(lambda p: 255 if p > 0 else 0)
    dilated = mask_binary.filter(ImageFilter.MaxFilter(thickness))
    eroded = mask_binary.filter(ImageFilter.MinFilter(thickness))
    return ImageChops.subtract(dilated, eroded)


def overlay_outline(img_path: Path, mask_path_: Path, max_dim: int = 700) -> tuple[Image.Image, Image.Image]:
    """Returns (plain_image, image_with_cyan_outline). The source image is
    decoded once; both outputs are derived from that single decode.
    """
    plain = load_resized_image(img_path, max_dim)
    outline = mask_outline(mask_path_, plain.size)
    cyan = Image.new("RGB", plain.size, OUTLINE_COLOR)
    outlined = Image.composite(cyan, plain, outline)
    return plain, outlined


def render(plantseg_dir: Path, tags_csv: Path, rows: list[dict], index: int | None, label: str = ""):
    total = len(rows)
    tags = load_tags(tags_csv)
    done = sum(1 for r in rows if r["name"] in tags)
    remaining = total - done

    if index is None:
        return None, None, f"✅ Class complete{label} — all {total} images tagged, 0 remaining."
    row = rows[index]
    plain, outlined = overlay_outline(image_path(plantseg_dir, row), mask_path(plantseg_dir, row))
    status = (
        f"{done}/{total}{label} tagged, {remaining} remaining — "
        f"{row['disease']} — split={row['split']} — {row['name']}"
    )
    return plain, outlined, status


def do_tag(plantseg_dir: Path, tags_csv: Path, rows: list[dict], tag_value: str, index: int | None):
    """Write `tag_value` for the image at `index`, then advance to the next
    untagged image (within `rows`). Returns (plain, outlined, status, next_index).
    """
    if index is not None:
        row = rows[index]
        append_tag(
            tags_csv, row["name"], row["plant"], row["disease"], row["split"],
            tag_value, datetime.now(timezone.utc).isoformat(),
        )
        index = next_untagged_index(rows, load_tags(tags_csv), start=index + 1)
    plain, outlined, status = render(plantseg_dir, tags_csv, rows, index)
    return plain, outlined, status, index


def do_undo(plantseg_dir: Path, tags_csv: Path, rows: list[dict], index: int | None):
    """Remove the most recently written tag and jump back to that image.
    Returns (plain, outlined, status, index).
    """
    removed_name = remove_last_tag(tags_csv)
    if removed_name is not None:
        removed_index = next((i for i, r in enumerate(rows) if r["name"] == removed_name), None)
        if removed_index is not None:
            index = removed_index
    plain, outlined, status = render(plantseg_dir, tags_csv, rows, index)
    return plain, outlined, status, index


def build_app(config: dict) -> gr.Blocks:
    plantseg_dir = Path(config["data"]["plantseg_dir"])
    tags_csv = tags_csv_path(config)
    disease_classes = config["disease_classes"]
    default_disease = "wheat leaf rust" if "wheat leaf rust" in disease_classes else disease_classes[0]

    # Plain closures (not gr.State) holding dict/list session data - gr.State
    # wrapping a dict/list triggers a gradio/pydantic schema-codegen crash on
    # page load (TypeError: argument of type 'bool' is not iterable), so only
    # simple scalars (int/None/str) go through gr.State; everything else is
    # looked up fresh or kept here. Fine for a single-user local tool.
    self_check = {"rows": [], "index": None, "results": []}

    with gr.Blocks(title="Wheat image tagging") as demo:
        gr.Markdown(RULES_REMINDER)
        btn_quit = gr.Button("Quit (q)", elem_id="tag-btn-quit", variant="stop")

        with gr.Tabs(selected="review"):
            with gr.Tab("Tag"):
                disease_dropdown = gr.Dropdown(
                    label="Disease class to tag", choices=disease_classes, value=default_disease,
                )
                tag_index_state = gr.State(None)
                with gr.Row():
                    image_display = gr.Image(label="original", interactive=False)
                    outline_display = gr.Image(label="lesion outline (cyan)", interactive=False)
                status_display = gr.Textbox(label="progress", interactive=False)
                with gr.Row():
                    btn_close_up = gr.Button("1: Close-up", elem_id="tag-btn-close-up")
                    btn_wide = gr.Button("2: Wide", elem_id="tag-btn-wide")
                    btn_non_photo = gr.Button("3: Non-photo", elem_id="tag-btn-non-photo")
                    btn_skip = gr.Button("4: Skip", elem_id="tag-btn-skip")
                    btn_undo = gr.Button("Undo last (Backspace)", elem_id="tag-btn-undo")

                def on_disease_change(disease):
                    rows = rows_for_disease(config, disease)
                    index = next_untagged_index(rows, load_tags(tags_csv))
                    plain, outlined, status = render(plantseg_dir, tags_csv, rows, index, label=f" ({disease})")
                    return plain, outlined, status, index

                def on_tag(tag_value, disease, index):
                    rows = rows_for_disease(config, disease)
                    plain, outlined, status, index = do_tag(plantseg_dir, tags_csv, rows, tag_value, index)
                    return plain, outlined, f"{status} ({disease})" if index is not None else status, index

                def on_undo(disease, index):
                    rows = rows_for_disease(config, disease)
                    plain, outlined, status, index = do_undo(plantseg_dir, tags_csv, rows, index)
                    return plain, outlined, status, index

                tag_outputs = [image_display, outline_display, status_display, tag_index_state]
                disease_dropdown.change(on_disease_change, [disease_dropdown], tag_outputs)
                demo.load(on_disease_change, [disease_dropdown], tag_outputs)

                btn_close_up.click(lambda d, i: on_tag("close_up", d, i), [disease_dropdown, tag_index_state], tag_outputs)
                btn_wide.click(lambda d, i: on_tag("wide", d, i), [disease_dropdown, tag_index_state], tag_outputs)
                btn_non_photo.click(lambda d, i: on_tag("non_photo", d, i), [disease_dropdown, tag_index_state], tag_outputs)
                btn_skip.click(lambda d, i: on_tag("skip", d, i), [disease_dropdown, tag_index_state], tag_outputs)
                btn_undo.click(on_undo, [disease_dropdown, tag_index_state], tag_outputs)

            with gr.Tab("Self-check (agreement test)"):
                gr.Markdown(
                    "Re-tag a balanced sample with tags hidden: ~20 random close_up images "
                    "plus *every* wide, non_photo, and skip image, shuffled together. Reports "
                    "agreement and Cohen's kappa, and saves to `report/tables/tagging_agreement.md`."
                )
                btn_start_sc = gr.Button("Start self-check (~20 close_up + all wide/non_photo/skip)")
                with gr.Row():
                    sc_image_display = gr.Image(label="original", interactive=False)
                    sc_outline_display = gr.Image(label="lesion outline (cyan)", interactive=False)
                sc_status_display = gr.Textbox(label="progress", interactive=False)
                with gr.Row():
                    sc_btn_close_up = gr.Button("1: Close-up", elem_id="sc-btn-close-up")
                    sc_btn_wide = gr.Button("2: Wide", elem_id="sc-btn-wide")
                    sc_btn_non_photo = gr.Button("3: Non-photo", elem_id="sc-btn-non-photo")
                    sc_btn_skip = gr.Button("4: Skip", elem_id="sc-btn-skip")
                sc_result_display = gr.Markdown()

                def sc_render():
                    total = len(self_check["rows"])
                    idx = self_check["index"]
                    if idx is None or idx >= total:
                        return None, None, ""
                    row = self_check["rows"][idx]
                    plain, outlined = overlay_outline(image_path(plantseg_dir, row), mask_path(plantseg_dir, row))
                    status = f"self-check {idx + 1}/{total} — {row['disease']} (tag hidden)"
                    return plain, outlined, status

                def sc_start():
                    all_rows = load_ordered_rows(config)
                    self_check["rows"] = sample_balanced_tagged_rows(all_rows, tags_csv, n_close_up=20)
                    self_check["index"] = 0
                    self_check["results"] = []
                    plain, outlined, status = sc_render()
                    return plain, outlined, status, ""

                def sc_answer(tag_value):
                    idx = self_check["index"]
                    if idx is None or idx >= len(self_check["rows"]):
                        return None, None, "Click 'Start self-check' first.", ""
                    row = self_check["rows"][idx]
                    self_check["results"].append((row["name"], row["disease"], row["original_tag"], tag_value))
                    self_check["index"] = idx + 1

                    if self_check["index"] >= len(self_check["rows"]):
                        summary = write_agreement_report(
                            self_check["results"], Path("report/tables/tagging_agreement.md")
                        )
                        kappa_str = f"{summary['kappa']:.3f}" if summary["kappa"] is not None else "n/a"
                        result_md = (
                            f"**Done.** Agreement: {summary['matches']}/{summary['n']} "
                            f"({summary['pct']:.1f}%), Cohen's kappa: {kappa_str}. "
                            f"Saved to report/tables/tagging_agreement.md"
                        )
                        return None, None, "Self-check complete.", result_md

                    plain, outlined, status = sc_render()
                    return plain, outlined, status, ""

                sc_outputs = [sc_image_display, sc_outline_display, sc_status_display, sc_result_display]
                btn_start_sc.click(sc_start, [], sc_outputs)
                sc_btn_close_up.click(lambda: sc_answer("close_up"), [], sc_outputs)
                sc_btn_wide.click(lambda: sc_answer("wide"), [], sc_outputs)
                sc_btn_non_photo.click(lambda: sc_answer("non_photo"), [], sc_outputs)
                sc_btn_skip.click(lambda: sc_answer("skip"), [], sc_outputs)

            with gr.Tab("Review", id="review"):
                gr.Markdown(
                    "Review already-tagged images. The current tag is shown - change it only if "
                    "needed; clicking **Next** moves on without changing anything."
                )
                review_list_names = list(REVIEW_LISTS)
                review_dropdown = gr.Dropdown(label="List to review", choices=review_list_names, value=review_list_names[0])
                with gr.Row():
                    rv_image_display = gr.Image(label="original", interactive=False)
                    rv_outline_display = gr.Image(label="lesion outline (cyan)", interactive=False)
                rv_status_display = gr.Textbox(label="progress", interactive=False)
                with gr.Row():
                    rv_btn_close_up = gr.Button("1: Close-up", elem_id="rv-btn-close-up")
                    rv_btn_wide = gr.Button("2: Wide", elem_id="rv-btn-wide")
                    rv_btn_non_photo = gr.Button("3: Non-photo", elem_id="rv-btn-non-photo")
                    rv_btn_skip = gr.Button("4: Skip", elem_id="rv-btn-skip")
                with gr.Row():
                    rv_btn_prev = gr.Button("← Previous", elem_id="rv-btn-prev")
                    rv_btn_next = gr.Button("Next → (keep tag)", elem_id="rv-btn-next")

                # Mutable closure (not gr.State - see note above) holding the
                # current review list and position within it.
                review = {"list_name": review_list_names[0], "rows": [], "index": 0}

                def rv_render():
                    rows = review["rows"]
                    total = len(rows)
                    if total == 0:
                        return None, None, "No images in this list."
                    idx = max(0, min(review["index"], total - 1))
                    review["index"] = idx
                    row = rows[idx]
                    plain, outlined = overlay_outline(image_path(plantseg_dir, row), mask_path(plantseg_dir, row))
                    return plain, outlined, review_status(row, idx, total, review["list_name"])

                def rv_select_list(list_name):
                    review["list_name"] = list_name
                    review["rows"] = REVIEW_LISTS[list_name](config)
                    review["index"] = 0
                    return rv_render()

                def rv_next():
                    review["index"] += 1
                    return rv_render()

                def rv_prev():
                    review["index"] -= 1
                    return rv_render()

                def rv_retag(tag_value):
                    rows = review["rows"]
                    idx = review["index"]
                    if rows and 0 <= idx < len(rows):
                        row = rows[idx]
                        append_tag(
                            tags_csv, row["name"], row["plant"], row["disease"], row["split"],
                            tag_value, datetime.now(timezone.utc).isoformat(),
                        )
                        row["tag"] = tag_value  # reflect the change immediately in this session
                    return rv_next()

                rv_outputs = [rv_image_display, rv_outline_display, rv_status_display]
                review_dropdown.change(rv_select_list, [review_dropdown], rv_outputs)
                demo.load(rv_select_list, [review_dropdown], rv_outputs)

                rv_btn_close_up.click(lambda: rv_retag("close_up"), [], rv_outputs)
                rv_btn_wide.click(lambda: rv_retag("wide"), [], rv_outputs)
                rv_btn_non_photo.click(lambda: rv_retag("non_photo"), [], rv_outputs)
                rv_btn_skip.click(lambda: rv_retag("skip"), [], rv_outputs)
                rv_btn_next.click(rv_next, [], rv_outputs)
                rv_btn_prev.click(rv_prev, [], rv_outputs)

        def quit_app():
            print("Quitting (q pressed / Quit button clicked).")
            os._exit(0)

        btn_quit.click(quit_app, [], [])
        demo.load(None, None, None, js=KEY_JS)

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    demo = build_app(config)
    demo.launch()


if __name__ == "__main__":
    main()
