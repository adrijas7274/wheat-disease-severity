"""Phase 3 annotation tool: leaf + lesion masks for the pilot / tuning / gold
sets, and the blind self-consistency recheck.

Rules: docs/annotation_guidelines.md. Tools: SAM 2 clicks, magic wand
(per-image tolerance slider with live preview) and brush. Lesion masks are
never pre-filled, and PlantSeg's own region mask is never shown, so the gold
masks don't lean on either the refinement pipeline or method A.

Usage:
    python -m src.severity.annotation_tool --config configs/config.yaml
then open the printed local URL.
"""

import argparse
import time
from pathlib import Path

import gradio as gr
import numpy as np
from PIL import Image

from src.data.wheat_metadata import image_path
from src.severity import annotation_core as core
from src.severity.annotation_sets import frozen_queues, pick_recheck, quota
from src.severity.sam2_model import load_sam2_predictor, predict_from_points
from src.severity.ui_zoom import CSS, ZOOM_JS, ZOOM_RESET_JS
from src.utils.config import load_config

# Display/brush copy only (masks are always full resolution). Large enough that
# zooming in on tiny rust pustules still shows real detail; sent as JPEG to keep
# each refresh small.
DISPLAY_MAX_SIDE = 2048
HISTORY_LIMIT = 30
SETS = ["pilot", "tuning", "gold", "recheck"]
MODES = ["SAM + (on object)", "SAM − (not object)", "Wand"]
STEP_MODE = {"leaf": MODES[0], "lesion": MODES[2]}  # default click mode when entering each step

LESION_HINTS = {  # short reminders; the full definitions are in docs/annotation_guidelines.md
    "wheat stripe rust": "Orange/yellow pustules (often in stripes). Mask pustules, not the green tissue between them.",
    "wheat leaf rust": "Orange-brown pustules. Mask pustules, not the green tissue between them.",
    "wheat powdery mildew": "White/greyish powdery coating. Not the green tissue under or near it.",
    "wheat septoria blotch": "Brown necrotic blotches incl. the dark dots (pycnidia) inside them.",
    "wheat bacterial leaf streak (black chaff)": "Brown or water-soaked streaks. If an edge is ambiguous, go tighter, not generous.",
}
CHLOROSIS_HINT = "Chlorotic (yellow) tissue: only where it touches/surrounds a masked lesion (PLACEHOLDER rule)."

CHECKLIST = {
    "leaf": [
        "Click mode <b>SAM +</b>: click on the <b>main leaf</b> (the leaf with the most visible disease).",
        "If the cyan spills onto other leaves/background: <b>SAM −</b> click there.",
        "<b>Add cyan to mask</b> (yellow outline = leaf).",
        "Fix edges in the <b>Brush</b> tab if needed (green add / magenta remove → Apply brush).",
        "Click <b>Leaf done → Step 2</b>.",
    ],
    "lesion": [
        "Click mode <b>Wand</b>: click <b>one</b> lesion spot.",
        "Drag the <b>tolerance slider</b> until the cyan matches the lesions.",
        "Scattered spots (rusts, mildew): <b>untick “connected region only”</b>.",
        "<b>Add cyan to mask</b> (red = lesion). Repeat for other lesion colours.",
        "Fix with the <b>Brush</b> tab, then <b>Save &amp; next</b>.",
        "No lesion visible on the main leaf? Tick <b>No visible lesion</b> before saving.",
    ],
}
STEP_STYLE = {"leaf": ("#fff3b0", "#8a6d00", "STEP 1 OF 2: LEAF MASK"),
              "lesion": ("#ffd6d6", "#a10000", "STEP 2 OF 2: LESION MASK")}



def banner_html(target: str, extra: str = "") -> str:
    """Big coloured step banner with that step's checklist."""
    bg, fg, title = STEP_STYLE[target]
    items = "".join(f"<li>{t}</li>" for t in CHECKLIST[target])
    warn = f"<p style='margin:6px 0 0;font-weight:bold'>⚠ {extra}</p>" if extra else ""
    return (f"<div style='background:{bg};color:{fg};border:3px solid {fg};border-radius:8px;padding:8px 12px'>"
            f"<div style='font-size:1.4em;font-weight:bold'>{title}</div>"
            f"<ol style='margin:4px 0 0 1.2em;color:{fg}'>{items}</ol>"
            f"<p style='margin:4px 0 0'>Zoom: scroll on the image · Pan: drag · <i>Reset zoom</i> button below.</p>{warn}</div>")


class Annotator:
    """Holds config, SAM predictor and the per-set queues; builds the UI."""

    def __init__(self, config: dict):
        self.config = config
        self.plantseg_dir = Path(config["data"]["plantseg_dir"])
        self.out_dir = Path(config["annotation"]["out_dir"])
        self.log_csv = self.out_dir / "annotation_log.csv"
        self.cap_s = 60 * config["annotation"]["lesion_time_cap_min"]
        self.tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
        # Freeze every set's queue BEFORE any re-tag can change eligibility (see frozen_queues).
        for s in ("pilot", "tuning", "gold"):
            frozen_queues(config, s, self.out_dir / "queues")
        self._sync_retags()
        self.predictor = load_sam2_predictor(config)

    def _sync_retags(self) -> None:
        for name in core.sync_not_photo_retags(self.log_csv, self.tags_csv):
            print(f"Re-tagged {name} -> non_photo in {self.tags_csv} (tag_source=human_annotation)")

    # ------------------------------------------------------------ queues

    def _queues_and_quotas(self, set_name: str) -> tuple[dict, dict]:
        if set_name == "recheck":
            gold_q, gold_quota = self._queues_and_quotas("gold")
            gold_status = core.load_status(self.log_csv, "gold")
            if not core.set_finished(core.progress(gold_q, gold_quota, gold_status)):
                raise gr.Error("The recheck opens only after the gold set is finished.")
            done = [n for n, r in gold_status.items() if r["status"] == "done"]
            picks = pick_recheck(done, self.config["annotation"]["recheck_n"], self.config["seed"])
            by_name = {r["name"]: r for q in gold_q.values() for r in q}
            return {"recheck": [by_name[n] for n in picks]}, {"recheck": len(picks)}
        queues = frozen_queues(self.config, set_name, self.out_dir / "queues")
        return queues, {d: quota(self.config, set_name, len(q)) for d, q in queues.items()}

    def _progress_md(self, set_name: str) -> str:
        queues, quotas = self._queues_and_quotas(set_name)
        rows = core.progress(queues, quotas, core.load_status(self.log_csv, set_name))
        lines = ["| disease | done / quota | skipped | incomplete |", "|---|---|---|---|"]
        for r in rows:
            flag = " (low-n)" if r["disease"] == "wheat leaf rust" and set_name == "gold" else ""
            lines.append(f"| {r['disease']}{flag} | {r['done']} / {r['quota']} | {r['skipped']} | {r['incomplete']} |")
        if core.set_finished(rows):
            lines.append(f"\n**{set_name} set finished.**")
        return "\n".join(lines)

    # ------------------------------------------------------------ state helpers

    def _tick(self, st: dict) -> None:
        """Add time since the last mark to the active step (leaf/lesion) unless paused."""
        t = st["timer"]
        now = time.monotonic()
        if not t["paused"]:
            t[f"{st['target']}_s"] += now - t["mark"]
        t["mark"] = now

    def _live_lesion_s(self, st: dict) -> float:
        t = st["timer"]
        live = 0.0 if t["paused"] or st["target"] != "lesion" else time.monotonic() - t["mark"]
        return t["lesion_s"] + live

    def _overlay(self, st: dict) -> np.ndarray:
        return core.render_overlay(st["image"], st["leaf"], st["lesion"], st["pending"], st["scale"])

    def _fragment_warning(self, st: dict) -> str:
        frac = core.largest_part_fraction(st["leaf"])
        if st["leaf"].any() and frac < core.FRAGMENT_WARN_BELOW:
            return (f"Leaf mask is in pieces (largest piece = {frac:.0%} of it). If there's no single "
                    f"main leaf, skip with “{core.NO_MAIN_LEAF}” (pre-selected on the right).")
        return ""

    def status_tick(self, st: dict | None):
        """Timer: refresh the status line and unlock 'Incomplete' once the lesion cap is reached."""
        if not st:
            return "No image loaded.", gr.update(interactive=False)
        t = st["timer"]
        live = 0.0 if t["paused"] else time.monotonic() - t["mark"]
        leaf_s = t["leaf_s"] + (live if st["target"] == "leaf" else 0)
        lesion_s = self._live_lesion_s(st)
        msg = (f"Step: **{st['target']}** | leaf {leaf_s / 60:.1f} min | lesion "
               f"{lesion_s / 60:.1f} / {self.cap_s / 60:.0f} min{' | PAUSED' if t['paused'] else ''}")
        capped = lesion_s >= self.cap_s
        if capped:
            msg += "\n\n**Lesion cap reached: save what you have and tick 'Incomplete'.**"
        return msg, gr.update(interactive=capped)

    def _push_history(self, st: dict) -> None:
        h = st["history"][st["target"]]
        h.append(st[st["target"]].copy())
        del h[:-HISTORY_LIMIT]

    def _commit(self, st: dict, new_mask: np.ndarray, tool: str) -> None:
        self._push_history(st)
        if st["target"] == "lesion":
            new_mask = new_mask & st["leaf"]  # lesions count on the main leaf only
        st[st["target"]] = new_mask
        st["tools"][st["target"]].add(tool)

    def _editor_value(self, st: dict) -> dict:
        return {"background": self._overlay(st), "layers": [], "composite": None}

    # ------------------------------------------------------------ handlers

    def load_next(self, set_name: str, st: dict | None):
        """Outputs: state, view, info, progress, editor, target, banner, mode, incomplete, notes, skip_reason, no_lesion."""
        reset = (gr.update(value=False, interactive=False), "", None, False)
        queues, quotas = self._queues_and_quotas(set_name)
        row = core.next_row(queues, quotas, core.load_status(self.log_csv, set_name))
        if row is None:
            return (None, None, "Nothing left to annotate in this set.", self._progress_md(set_name), None,
                    "leaf", banner_html("leaf"), MODES[0], *reset)
        image = np.array(Image.open(image_path(self.plantseg_dir, row)).convert("RGB"))
        self.predictor.set_image(image)
        empty = np.zeros(image.shape[:2], bool)
        st = {
            "set": set_name, "row": row, "image": image, "lab": None,
            "scale": core.display_scale(image.shape, DISPLAY_MAX_SIDE),
            "leaf": empty.copy(), "lesion": empty.copy(), "pending": None,
            "clicks": [], "wand_seed": None, "target": "leaf",
            "history": {"leaf": [], "lesion": []}, "tools": {"leaf": set(), "lesion": set()},
            "tolerances": [],
            "timer": {"leaf_s": 0.0, "lesion_s": 0.0, "mark": time.monotonic(), "paused": False},
        }
        hint = LESION_HINTS.get(row["disease"], "")
        info = (f"**{row['name']}**: {row['disease']} ({row['split']}, {image.shape[1]}×{image.shape[0]} px)  \n"
                f"Lesion: {hint}  \n{CHLOROSIS_HINT}")
        if set_name == "recheck":
            info = "**Blind recheck**: annotate from scratch as if new.  \n" + info
        return (st, self._overlay(st), info, self._progress_md(set_name), self._editor_value(st),
                "leaf", banner_html("leaf"), MODES[0], *reset)

    def set_target(self, target: str, st: dict):
        """Outputs: state, view, target, banner, mode, skip_reason."""
        if not st:
            return st, None, "leaf", banner_html("leaf"), gr.update(), gr.update()
        if target == "lesion" and not st["leaf"].any():
            gr.Warning("Do the leaf mask first: lesions are clipped to the main leaf.")
            return st, self._overlay(st), "leaf", banner_html("leaf"), gr.update(), gr.update()
        if target == "lesion" and st["pending"] is not None and st["target"] == "leaf":
            gr.Warning("There's an uncommitted (cyan) leaf selection: add or clear it first.")
            return st, self._overlay(st), "leaf", banner_html("leaf"), gr.update(), gr.update()
        self._tick(st)
        st["target"], st["pending"], st["clicks"], st["wand_seed"] = target, None, [], None
        warn = self._fragment_warning(st) if target == "lesion" else ""
        skip = core.NO_MAIN_LEAF if warn else gr.update()
        return st, self._overlay(st), target, banner_html(target, warn), STEP_MODE[target], skip

    def _pending_from_wand(self, st: dict, tol: float, contiguous: bool) -> None:
        if st["lab"] is None:
            st["lab"] = core.to_lab(st["image"])
        sel = core.wand_select(st["lab"], st["wand_seed"], tol, contiguous)
        st["pending"] = sel & st["leaf"] if st["target"] == "lesion" else sel

    def on_click(self, mode: str, tol: float, contiguous: bool, st: dict, evt: gr.SelectData):
        if not st:
            return st, None
        self._tick(st)
        x = min(st["image"].shape[1] - 1, int(evt.index[0] / st["scale"]))
        y = min(st["image"].shape[0] - 1, int(evt.index[1] / st["scale"]))
        if mode == "Wand":
            st["clicks"], st["wand_seed"] = [], (x, y)
            self._pending_from_wand(st, tol, contiguous)
        else:
            st["wand_seed"] = None
            st["clicks"].append((x, y, 1 if mode.startswith("SAM +") else 0))
            if not any(lab == 1 for *_, lab in st["clicks"]):
                gr.Info("Add at least one SAM + click on the object.")
                return st, self._overlay(st)
            m = predict_from_points(self.predictor, st["clicks"])
            st["pending"] = m & st["leaf"] if st["target"] == "lesion" else m
        return st, self._overlay(st)

    def on_wand_params(self, tol: float, contiguous: bool, st: dict):
        """Live preview: re-run the wand from the same seed when the slider moves."""
        if not st or st["wand_seed"] is None:
            return st, gr.update()
        self._pending_from_wand(st, tol, contiguous)
        return st, self._overlay(st)

    def commit_pending(self, add: bool, tol: float, st: dict):
        if not st or st["pending"] is None:
            return st, gr.update()
        self._tick(st)
        tool = "wand" if st["wand_seed"] is not None else "sam"
        if tool == "wand":
            st["tolerances"].append(round(float(tol), 1))
        cur = st[st["target"]]
        self._commit(st, (cur | st["pending"]) if add else (cur & ~st["pending"]), tool)
        st["pending"], st["clicks"], st["wand_seed"] = None, [], None
        return st, self._overlay(st)

    def clear_pending(self, st: dict):
        if not st:
            return st, gr.update()
        st["pending"], st["clicks"], st["wand_seed"] = None, [], None
        return st, self._overlay(st)

    def undo(self, st: dict):
        if not st or not st["history"][st["target"]]:
            return st, gr.update()
        st[st["target"]] = st["history"][st["target"]].pop()
        st["pending"] = None
        return st, self._overlay(st)

    def refresh_editor(self, st: dict):
        return self._editor_value(st) if st else None

    def apply_brush(self, editor: dict | None, st: dict):
        if not st or not editor or not editor.get("layers"):
            return st, gr.update(), gr.update()
        self._tick(st)
        new = st[st["target"]]
        for layer in editor["layers"]:
            if layer is not None and layer.ndim == 3 and layer.shape[2] == 4:
                new = core.apply_brush_layer(new, layer)
        self._commit(st, new, "brush")
        return st, self._overlay(st), self._editor_value(st)

    def toggle_pause(self, st: dict):
        if not st:
            return st, "Pause timer"
        self._tick(st)
        st["timer"]["paused"] = not st["timer"]["paused"]
        return st, "Resume timer" if st["timer"]["paused"] else "Pause timer"

    def _base_row(self, st: dict, annotator: str) -> dict:
        if not annotator.strip():
            raise gr.Error("Enter your name in 'Annotator' first.")
        r = st["row"]
        return {"name": r["name"], "split": r["split"], "disease": r["disease"], "set": st["set"],
                "annotator": annotator.strip(), "saved_at": core.now_iso()}

    def save(self, annotator: str, incomplete: bool, no_lesion: bool, notes: str, st: dict):
        if not st:
            raise gr.Error("No image loaded.")
        if not st["leaf"].any():
            raise gr.Error("Leaf mask is empty.")
        if st["pending"] is not None:
            raise gr.Error("There's an uncommitted (cyan) selection: add, subtract or clear it first.")
        if st["target"] != "lesion":
            raise gr.Error("You're still on Step 1 (leaf). Click 'Leaf done → Step 2' and mask the lesions.")
        lesion = st["lesion"] & st["leaf"]
        if not lesion.any() and not no_lesion:
            raise gr.Error("Lesion mask is empty. Mask the lesions, or tick 'No visible lesion on main leaf'.")
        if lesion.any() and no_lesion:
            raise gr.Error("'No visible lesion' is ticked but the lesion mask isn't empty: untick it or clear the mask.")
        self._tick(st)
        if incomplete and st["timer"]["lesion_s"] < self.cap_s:
            raise gr.Error("'Incomplete' is only for images where the lesion time cap was reached.")
        row = self._base_row(st, annotator) | {
            "status": "done", "incomplete": "true" if incomplete else "false",
            "leaf_s": round(st["timer"]["leaf_s"], 1), "lesion_s": round(st["timer"]["lesion_s"], 1),
            "tools_leaf": "+".join(sorted(st["tools"]["leaf"])), "tools_lesion": "+".join(sorted(st["tools"]["lesion"])),
            "wand_tolerance": ";".join(map(str, st["tolerances"])),
            "leaf_px": int(st["leaf"].sum()), "lesion_px": int(lesion.sum()),
            "severity": round(core.severity(st["leaf"], lesion), 5),
            "no_lesion": "true" if no_lesion else "false",
            "leaf_largest_part": round(core.largest_part_fraction(st["leaf"]), 3),
            "notes": notes.strip(),
        }
        core.save_masks(self.out_dir, st["set"], row["name"], st["leaf"], lesion)
        core.append_log(self.log_csv, row)
        gr.Info(f"Saved {row['name']}: severity {row['severity']:.3f}, "
                f"{(row['leaf_s'] + row['lesion_s']) / 60:.1f} min")
        return self.load_next(st["set"], st)

    def skip(self, annotator: str, reason: str | None, notes: str, st: dict):
        if not st:
            raise gr.Error("No image loaded.")
        if not reason:
            raise gr.Error("Pick a skip reason (only the listed reasons are allowed).")
        if st["set"] == "recheck":
            raise gr.Error("Recheck images can't be skipped: they were already annotated once.")
        self._tick(st)
        core.append_log(self.log_csv, self._base_row(st, annotator) | {
            "status": "skipped", "skip_reason": reason, "notes": notes.strip(),
            "leaf_s": round(st["timer"]["leaf_s"], 1), "lesion_s": round(st["timer"]["lesion_s"], 1),
            "leaf_largest_part": round(core.largest_part_fraction(st["leaf"]), 3) if st["leaf"].any() else "",
        })
        if reason == core.NOT_A_PHOTO:
            self._sync_retags()
            gr.Info(f"{st['row']['name']} re-tagged as non_photo in the tags CSV.")
        return self.load_next(st["set"], st)

    # ------------------------------------------------------------ UI

    def build(self) -> gr.Blocks:
        with gr.Blocks(title="Wheat leaf + lesion annotation", css=CSS) as demo:
            st = gr.State(None)
            gr.Markdown("## Leaf + lesion annotation (rules: `docs/annotation_guidelines.md`)")
            with gr.Row():
                set_dd = gr.Dropdown(SETS, value="pilot", label="Set", scale=1)
                annotator = gr.Textbox(label="Annotator", scale=1)
                load_btn = gr.Button("Load next image", variant="primary", scale=1)
            with gr.Row():
                with gr.Column(scale=3):
                    banner = gr.HTML(banner_html("leaf"))
                    info = gr.Markdown()
                    with gr.Row():
                        target = gr.Radio(["leaf", "lesion"], value="leaf", label="Step (go back to 'leaf' to fix it)", scale=2)
                        leaf_done_btn = gr.Button("Leaf done → Step 2", variant="primary", scale=1)
                    with gr.Tabs():
                        with gr.Tab("Click tools (SAM / wand)"):
                            view = gr.Image(label="Click to add points / wand seed", interactive=False, format="jpeg",
                                            show_download_button=False, show_fullscreen_button=False, elem_id="zoom-view")
                            with gr.Row():
                                mode = gr.Radio(MODES, value=MODES[0], label="Click mode")
                                tol = gr.Slider(1, 60, value=15, step=0.5, label="Wand tolerance (colour distance, set per image)")
                                contiguous = gr.Checkbox(True, label="Wand: connected region only")
                            with gr.Row():
                                add_btn = gr.Button("Add cyan to mask", variant="primary")
                                sub_btn = gr.Button("Subtract cyan from mask")
                                clr_btn = gr.Button("Clear cyan")
                                undo_btn = gr.Button("Undo last change")
                                zoom_btn = gr.Button("Reset zoom")
                        with gr.Tab("Brush") as brush_tab:
                            gr.Markdown("Paint **green = add**, **magenta = remove** on the current step's mask, then *Apply brush*.")
                            editor = gr.ImageEditor(
                                type="numpy", label="Brush", sources=(), transforms=(), eraser=gr.Eraser(),
                                brush=gr.Brush(colors=["#00ff00", "#ff00ff"], default_color="#00ff00", color_mode="fixed"),
                                show_download_button=False,
                            )
                            with gr.Row():
                                apply_btn = gr.Button("Apply brush", variant="primary")
                                undo_btn2 = gr.Button("Undo last change")
                with gr.Column(scale=1):
                    status = gr.Markdown("No image loaded.")
                    pause_btn = gr.Button("Pause timer")
                    no_lesion = gr.Checkbox(False, label="No visible lesion on main leaf")
                    incomplete = gr.Checkbox(False, interactive=False,
                                             label=f"Incomplete (unlocks when the {self.cap_s // 60:.0f}-min lesion cap is reached)")
                    notes = gr.Textbox(label="Notes (ambiguous main leaf, etc.)", lines=3)
                    save_btn = gr.Button("Save & next", variant="primary")
                    skip_reason = gr.Dropdown(core.SKIP_REASONS, value=None, label="Skip reason")
                    skip_btn = gr.Button("Skip (logged) & next", variant="stop")
                    progress_md = gr.Markdown()
            timer = gr.Timer(5)

            load_out = [st, view, info, progress_md, editor, target, banner, mode,
                        incomplete, notes, skip_reason, no_lesion]
            target_out = [st, view, target, banner, mode, skip_reason]
            load_btn.click(self.load_next, [set_dd, st], load_out).then(None, None, None, js=ZOOM_RESET_JS)
            set_dd.change(lambda s: self._progress_md(s), set_dd, progress_md)
            target.input(self.set_target, [target, st], target_out)
            leaf_done_btn.click(lambda s: self.set_target("lesion", s), st, target_out)
            view.select(self.on_click, [mode, tol, contiguous, st], [st, view])
            tol.release(self.on_wand_params, [tol, contiguous, st], [st, view])
            contiguous.change(self.on_wand_params, [tol, contiguous, st], [st, view])
            mode.input(self.clear_pending, st, [st, view])
            add_btn.click(lambda t, s: self.commit_pending(True, t, s), [tol, st], [st, view])
            sub_btn.click(lambda t, s: self.commit_pending(False, t, s), [tol, st], [st, view])
            clr_btn.click(self.clear_pending, st, [st, view])
            undo_btn.click(self.undo, st, [st, view])
            zoom_btn.click(None, None, None, js=ZOOM_RESET_JS)
            undo_btn2.click(self.undo, st, [st, view]).then(self.refresh_editor, st, editor)
            brush_tab.select(self.refresh_editor, st, editor)
            apply_btn.click(self.apply_brush, [editor, st], [st, view, editor])
            pause_btn.click(self.toggle_pause, st, [st, pause_btn])
            save_btn.click(self.save, [annotator, incomplete, no_lesion, notes, st], load_out).then(
                None, None, None, js=ZOOM_RESET_JS)
            skip_btn.click(self.skip, [annotator, skip_reason, notes, st], load_out).then(
                None, None, None, js=ZOOM_RESET_JS)
            timer.tick(self.status_tick, st, [status, incomplete])
            demo.load(lambda s: self._progress_md(s), set_dd, progress_md)
            demo.load(None, None, None, js=ZOOM_JS)
        return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 leaf + lesion annotation tool")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    Annotator(load_config(args.config)).build().launch(server_port=args.port)


if __name__ == "__main__":
    main()
