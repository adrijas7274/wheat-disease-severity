"""Phase 3 visual severity rating tool (gold standard, replaces the mask tool).

For each image in the set's frozen queue: zoom/pan the photo, click once on
the main leaf (point stored), enter severity % with the standard area
diagrams as reference, save or skip. Shows only the photo and the click
marker. No PlantSeg mask, model output or SAM result is ever displayed (see
docs/annotation_guidelines.md, "Independence from the pipeline").

Usage:
    python -m src.severity.rating_tool --config configs/config.yaml
then open the printed local URL.
"""

import argparse
import secrets
import time
from pathlib import Path

import cv2
import gradio as gr
import numpy as np
from PIL import Image

from src.data.wheat_metadata import image_path
from src.severity import annotation_core as core
from src.severity import area_diagrams as sad
from src.severity import rater_training as rt
from src.severity import rating_core as rc
from src.severity.annotation_sets import frozen_queues, pick_recheck, quota
from src.severity.ui_zoom import CSS, ZOOM_JS, ZOOM_RESET_JS
from src.utils.config import load_config

N_LOAD_OUTPUTS = 13  # state + 12 components, see load_next
# Number box and slider may differ by snapping (slider step 0.5) but not by a
# whole step: a bigger gap means a sync event hasn't landed yet.
SYNC_TOLERANCE = 0.25
SETS = ["pilot", "tuning", "gold", "recheck"]
SET_TITLES = {"pilot": "Pilot", "tuning": "Tuning", "gold": "Gold", "recheck": "Recheck"}

LESION_HINTS = {  # short reminders; full definitions in docs/annotation_guidelines.md
    "wheat stripe rust": "orange/yellow pustules (often in stripes), not the green tissue between them",
    "wheat leaf rust": "orange-brown pustules, not the green tissue between them",
    "wheat powdery mildew": "the white/greyish powdery coating, not the green tissue under or near it",
    "wheat septoria blotch": "brown necrotic blotches, including the dark dots (pycnidia) inside them",
    "wheat bacterial leaf streak (black chaff)": "brown or water-soaked streaks; if an edge is ambiguous, go tighter",
}
STEPS_HTML = """
<div style='background:#eef6ff;border:2px solid #2b6cb0;border-radius:8px;padding:8px 12px;color:#1a365d'>
<b style='font-size:1.15em'>For each image</b>
<ol style='margin:4px 0 0 1.2em'>
<li><b>Look</b> at the whole photo. Zoom: scroll on it · Pan: drag.</li>
<li><b>Click once on the main leaf</b> (the leaf with the most disease), mid-width, on healthy-looking tissue. Click again to move it.</li>
<li>Compare with the <b>reference diagrams</b> → type or slide the <b>severity %</b> of <i>that leaf's visible area</i> covered by lesions.</li>
<li><b>Save &amp; next</b>. Can't rate it for a listed reason? Pick it and <b>Skip</b>.</li>
</ol></div>
"""
LESION_REMINDER = "**Count only lesion/pustule area on the main leaf, not the green tissue between spots.**"
TRAINING_HTML = """
<div style='background:#f0fff4;border:2px solid #2f855a;border-radius:8px;padding:8px 12px;color:#1c4532'>
<b style='font-size:1.15em'>Rater training (practice only, never saved to any rating log)</b>
<ol style='margin:4px 0 0 1.2em'>
<li><b>Start new training set</b>: 15 synthetic leaves with hidden, exactly known severity.</li>
<li>Estimate the % of the leaf covered by lesions (diagram on the right for reference) → <b>Submit rating</b>.</li>
<li>Read the true value and your error → <b>Next leaf</b>.</li>
<li>After leaf 15 you get your mean error and whether you over- or underestimate (saved to <code>report/tables/rater_training.md</code>).</li>
</ol></div>
"""


class Rater:
    """Holds config and log paths; builds the UI."""

    def __init__(self, config: dict):
        self.config = config
        self.plantseg_dir = Path(config["data"]["plantseg_dir"])
        self.out_dir = Path(config["annotation"]["out_dir"])
        self.log_csv = self.out_dir / config["annotation"]["rating_log"]
        self.mask_log_csv = self.out_dir / "annotation_log.csv"  # retired mask tool's log
        self.tags_csv = Path(config["data"]["processed_dir"]) / f"{config['crop']}_tags.csv"
        self.training_report = Path(config["annotation"].get("training_report", rt.DEFAULT_REPORT))
        ui = config["annotation"].get("ui", {})
        self.default_set = ui.get("default_set", "tuning")
        self.default_rater = ui.get("default_rater", "")
        self.break_every = int(ui.get("break_every", 20))
        for s in ("pilot", "tuning", "gold"):  # freeze before any re-tag (see frozen_queues)
            frozen_queues(config, s, self.out_dir / "queues")
        self._sync_retags()
        if not all(sad.panel_path(s).exists() for s in sad.STYLES):
            sad.generate_all(config["seed"])

    def _sync_retags(self) -> None:
        for name in core.sync_not_photo_retags(self.log_csv, self.tags_csv, rc.RETAG_REASONS):
            print(f"Re-tagged {name} -> non_photo in {self.tags_csv} (tag_source=human_annotation)")

    # ------------------------------------------------------------ queues

    def _status(self, set_name: str) -> dict[str, dict]:
        exclude = rc.seen_in_mask_pilots(self.mask_log_csv) if set_name == "pilot" else set()
        return rc.status_with_exclusions(self.log_csv, set_name, exclude)

    def _queues_and_quotas(self, set_name: str) -> tuple[dict, dict]:
        if set_name == "recheck":
            gold_q, gold_quota = self._queues_and_quotas("gold")
            gold_status = self._status("gold")
            if not core.set_finished(core.progress(gold_q, gold_quota, gold_status)):
                raise ValueError("The recheck opens only after the gold set is finished.")
            done = [n for n, r in gold_status.items() if r["status"] == "done"]
            picks = pick_recheck(done, self.config["annotation"]["recheck_n"], self.config["seed"])
            by_name = {r["name"]: r for q in gold_q.values() for r in q}
            return {"recheck": [by_name[n] for n in picks]}, {"recheck": len(picks)}
        queues = frozen_queues(self.config, set_name, self.out_dir / "queues")
        return queues, {d: quota(self.config, set_name, len(q)) for d, q in queues.items()}

    def _progress_md(self, set_name: str) -> str:
        try:
            queues, quotas = self._queues_and_quotas(set_name)
        except ValueError:
            return "Recheck opens after the gold set is finished."
        rows = core.progress(queues, quotas, self._status(set_name))
        lines = ["| disease | done / quota | skipped |", "|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['disease']} | {r['done']} / {r['quota']} | {r['skipped']} |")
        if core.set_finished(rows):
            lines.append(f"\n**{set_name} set finished.**")
        return "\n".join(lines)

    def _counter_html(self, set_name: str) -> str:
        """Big progress counter, e.g. 'Gold: 12 / 54 rated'. Skips don't count toward the quota."""
        try:
            queues, quotas = self._queues_and_quotas(set_name)
        except ValueError:
            return (f"<div style='font-size:1.6em;font-weight:bold'>{SET_TITLES[set_name]}: "
                    f"opens after the gold set is finished</div>")
        rows = core.progress(queues, quotas, self._status(set_name))
        done, total = sum(r["done"] for r in rows), sum(r["quota"] for r in rows)
        skipped = sum(r["skipped"] for r in rows)
        pct = 100 * done / total if total else 0
        tail = f" &nbsp;<span style='font-size:0.6em;font-weight:normal'>({skipped} skipped)</span>" if skipped else ""
        return (f"<div style='font-size:1.8em;font-weight:bold'>{SET_TITLES[set_name]}: {done} / {total} rated{tail}</div>"
                f"<div style='background:#e2e8f0;border-radius:6px;height:12px;margin-top:4px'>"
                f"<div style='background:#2f855a;width:{pct:.1f}%;height:12px;border-radius:6px'></div></div>")

    # ------------------------------------------------------------ helpers

    def _elapsed(self, st: dict) -> float:
        t = st["timer"]
        return t["acc"] + (0.0 if t["paused"] else time.monotonic() - t["mark"])

    def _view(self, st: dict) -> np.ndarray:
        return rc.draw_marker(st["display"], st["click"], st["scale"])

    def _click_md(self, st: dict | None) -> str:
        if not st or st["click"] is None:
            return "Main leaf: **not clicked yet**"
        return f"Main leaf: clicked at ({st['click'][0]}, {st['click'][1]}) ✔"

    def _base_row(self, st: dict, rater: str) -> dict:
        if not rater.strip():
            raise ValueError("Enter your name in 'Rater' first.")
        if st["set"] == "gold" and self.config["annotation"].get("gold_locked"):
            raise ValueError("Gold ratings are locked. Nothing was saved (only the logged recheck is open).")
        r = st["row"]
        return {"name": r["name"], "split": r["split"], "disease": r["disease"], "set": st["set"],
                "rater": rater.strip(), "rating_s": round(self._elapsed(st), 1), "saved_at": core.now_iso()}

    @staticmethod
    def _refuse(msg: str, st: dict | None) -> tuple:
        """Warn and leave every output as it is. Never gr.Error here: Gradio
        then covers all of the event's outputs (photo included) with an
        "Error" overlay that hides the image and swallows clicks."""
        gr.Warning(msg)
        return (st, *[gr.update()] * (N_LOAD_OUTPUTS - 1))

    # ------------------------------------------------------------ handlers

    def load_next(self, set_name: str, st: dict | None = None, notice: str = ""):
        """Outputs: state, view, info, click_md, progress, severity, slider, notes, skip_reason, ref_tabs,
        pause_btn, set_dd, counter. `st` is the previous image's state (its session count carries over)."""
        try:
            queues, quotas = self._queues_and_quotas(set_name)
        except ValueError as e:
            return self._refuse(str(e), st)
        n_session = st.get("n_session", 0) if st else 0
        row = core.next_row(queues, quotas, self._status(set_name))
        cleared = (None, 0, "", None)
        if row is None and set_name == "tuning":
            msg = ("✔ **Tuning set finished.** Switched to the **gold set**. "
                   "Take a short break first if you like: the gold set is the one that counts.")
            gr.Info("Tuning set finished. Switched to the gold set.", duration=10)
            carry = {"n_session": n_session}
            return self.load_next("gold", carry, notice=msg)
        if row is None:
            done_msg = {
                "gold": ("✔ **Gold set finished. Thank you!** Ask Claude to check the ratings. "
                         "Do the recheck in a later session, not right away."),
                "tuning": "✔ **Tuning set finished.**",
            }.get(set_name, f"✔ **Nothing left to rate in the {set_name} set.**")
            return (None, None, done_msg, self._click_md(None), self._progress_md(set_name), *cleared,
                    gr.update(), "Pause timer", gr.update(value=set_name), self._counter_html(set_name))
        image = np.array(Image.open(image_path(self.plantseg_dir, row)).convert("RGB"))
        scale = rc.rating_display_scale(image.shape)  # display only; clicks are mapped back to original px
        size = (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale)))
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        st = {"set": set_name, "row": row, "shape": image.shape, "scale": scale,
              "display": cv2.resize(image, size, interpolation=interp), "click": None, "confirm_high": None,
              "n_session": n_session,
              "timer": {"acc": 0.0, "mark": time.monotonic(), "paused": False}}
        # Disease + lesion definition only: no file name, split or any dataset/pipeline detail.
        info = (f"### {row['disease']}\n"
                f"**Lesion =** {LESION_HINTS.get(row['disease'], '')}.  \n"
                f"Chlorotic halo only where it touches a lesion (PLACEHOLDER rule).")
        if notice:
            info = notice + "\n\n" + info
        if set_name == "recheck":
            info = "**Blind recheck: rate from scratch, as if new.**\n\n" + info
        style = sad.DISEASE_STYLE.get(row["disease"], "rust")
        return (st, self._view(st), info, self._click_md(st), self._progress_md(set_name), *cleared,
                gr.Tabs(selected=style), "Pause timer", gr.update(value=set_name), self._counter_html(set_name))

    def _after_action(self, st: dict):
        """Count the image toward this session, nudge a break every `break_every` images, load the next one."""
        st["n_session"] = st.get("n_session", 0) + 1
        if self.break_every and st["n_session"] % self.break_every == 0:
            gr.Info(f"{st['n_session']} images done this session: a good moment for a short break. "
                    "Stretch, rest your eyes, and use 'Pause timer' if you step away.", duration=20)
        return self.load_next(st["set"], st)

    def on_click(self, st: dict | None, evt: gr.SelectData):
        if not st:
            return st, None, self._click_md(None)
        st["click"] = rc.display_to_image(evt.index, st["scale"], st["shape"])
        return st, self._view(st), self._click_md(st)

    def toggle_pause(self, st: dict | None):
        if not st:
            return st, "Pause timer"
        t = st["timer"]
        now = time.monotonic()
        if not t["paused"]:
            t["acc"] += now - t["mark"]
        t["mark"], t["paused"] = now, not t["paused"]
        return st, "Resume timer" if t["paused"] else "Pause timer"

    def status_tick(self, st: dict | None) -> str:
        if not st:
            return "No image loaded."
        paused = " | **PAUSED**" if st["timer"]["paused"] else ""
        return f"Time on this image: {self._elapsed(st) / 60:.1f} min{paused}"

    def save(self, rater: str, severity_pct: float | None, slider_pct: float | None, notes: str, st: dict | None):
        if not st:
            return self._refuse("No image loaded.", st)
        try:
            rc.validate_rating(st["click"], severity_pct)
            if slider_pct is not None and abs(float(slider_pct) - float(severity_pct)) > SYNC_TOLERANCE:
                raise ValueError(f"Number box ({severity_pct}) and slider ({slider_pct}) disagree. "
                                 "Set the value again, then save.")
            base = self._base_row(st, rater)
        except ValueError as e:
            return self._refuse(str(e), st)
        value = float(severity_pct)
        if rc.needs_high_confirm(value, st.get("confirm_high")):
            st["confirm_high"] = value
            return self._refuse(f"{value:g}% is above 75%, the highest reference diagram. Check that you counted "
                                f"only lesion area, not the green tissue between spots. "
                                f"Click Save again to confirm {value:g}%, or change the value.", st)
        row = base | {
            "status": "done", "click_x": st["click"][0], "click_y": st["click"][1],
            "img_w": st["shape"][1], "img_h": st["shape"][0],
            "severity_pct": round(float(severity_pct), 2), "notes": notes.strip(),
        }
        core.append_log(self.log_csv, row, rc.RATING_FIELDNAMES)
        gr.Info(f"Saved: {row['severity_pct']}%")
        return self._after_action(st)

    def skip(self, rater: str, reason: str | None, notes: str, st: dict | None):
        if not st:
            return self._refuse("No image loaded.", st)
        if not reason:
            return self._refuse("Pick a skip reason (only the listed reasons are allowed).", st)
        if st["set"] == "recheck":
            return self._refuse("Recheck images can't be skipped: they were already rated once.", st)
        try:
            base = self._base_row(st, rater)
        except ValueError as e:
            return self._refuse(str(e), st)
        row = base | {"status": "skipped", "skip_reason": reason, "notes": notes.strip()}
        if st["click"] is not None:
            row |= {"click_x": st["click"][0], "click_y": st["click"][1]}
        row |= {"img_w": st["shape"][1], "img_h": st["shape"][0]}
        core.append_log(self.log_csv, row, rc.RATING_FIELDNAMES)
        if reason in rc.RETAG_REASONS:
            self._sync_retags()
        gr.Info(f"Skipped ({reason}).")
        return self._after_action(st)

    # ------------------------------------------------------------ rater training

    def _train_outputs(self, tr: dict, feedback: str = "") -> tuple:
        """Outputs: tr_state, tr_img, tr_info, tr_num, tr_feedback, tr_ref."""
        leaf = tr["session"].leaves[tr["idx"]]
        info = (f"### Training leaf {tr['idx'] + 1} of {len(tr['session'].leaves)}: {leaf.style}-like lesions\n"
                "What % of the leaf's area is covered by lesions?")
        return (tr, rt.render(leaf, flip=tr["flips"][tr["idx"]]), info, None, feedback,
                str(sad.panel_path(leaf.style)))

    def train_start(self, tr: dict | None):
        seed = secrets.randbits(31)
        session = rt.make_session(seed)
        flips = [bool(b) for b in np.random.default_rng(seed).integers(0, 2, len(session.leaves))]
        return self._train_outputs({"session": session, "idx": 0, "answered": False, "flips": flips, "saved": False})

    def train_submit(self, value: float | None, rater: str, tr: dict | None):
        keep = (tr, *[gr.update()] * 5)
        if not tr:
            gr.Warning("Click 'Start new training set' first.")
            return keep
        if tr["answered"]:
            gr.Warning("Already rated: click 'Next leaf'." if tr["idx"] + 1 < len(tr["session"].leaves)
                       else "Set finished: click 'Start new training set' to do another 15.")
            return keep
        if value is None or not 0 <= value <= 100:
            gr.Warning("Enter a severity between 0 and 100.")
            return keep
        leaf = tr["session"].leaves[tr["idx"]]
        leaf.rating = float(value)
        tr["answered"] = True
        err = leaf.error
        direction = "over" if err > 0 else "under" if err < 0 else "exact"
        fb = (f"**True: {leaf.true_pct:.1f}%** · You: {leaf.rating:g}% · "
              f"Error: **{err:+.1f}** points ({direction}{'estimate' if direction != 'exact' else ''})")
        if tr["idx"] + 1 == len(tr["session"].leaves):
            sm = rt.summary(tr["session"])
            rt.append_report(self.training_report, tr["session"], rater.strip())
            tr["saved"] = True
            by_style = " · ".join(f"{k}: MAE {v['mae']:.1f}, signed {v['bias']:+.1f}" for k, v in sm["by_style"].items())
            fb += (f"\n\n---\n### Set finished\n**Mean absolute error: {sm['mae']:.1f} percentage points** "
                   f"over {sm['n']} leaves.  \n{rt.bias_sentence(sm['bias'])}  \nBy style: {by_style}  \n"
                   f"Saved to `{self.training_report.as_posix()}`. Click *Start new training set* to do another 15.")
        return (tr, gr.update(), gr.update(), gr.update(), fb, gr.update())

    def train_next(self, tr: dict | None):
        keep = (tr, *[gr.update()] * 5)
        if not tr:
            gr.Warning("Click 'Start new training set' first.")
            return keep
        if not tr["answered"]:
            gr.Warning("Rate this leaf first, then click 'Next leaf'.")
            return keep
        if tr["idx"] + 1 >= len(tr["session"].leaves):
            gr.Warning("Set finished: click 'Start new training set' to do another 15.")
            return keep
        tr["idx"] += 1
        tr["answered"] = False
        return self._train_outputs(tr)

    # ------------------------------------------------------------ UI

    def build(self) -> gr.Blocks:
        with gr.Blocks(title="Wheat severity rating", css=CSS) as demo:
            st = gr.State(None)
            tr_state = gr.State(None)
            gr.Markdown("## Visual severity rating (rules: `docs/annotation_guidelines.md`)")
            rater = gr.Textbox(label="Rater", value=self.default_rater, max_lines=1)
            with gr.Tabs():
                with gr.Tab("Rate images"):
                    with gr.Row():
                        set_dd = gr.Dropdown(SETS, value=self.default_set, label="Set", scale=1)
                        load_btn = gr.Button("Load next image", variant="primary", scale=1)
                    counter = gr.HTML(self._counter_html(self.default_set))
                    with gr.Row():
                        with gr.Column(scale=3):
                            info = gr.Markdown()
                            view = gr.Image(label="Photo: click once on the main leaf", interactive=False,
                                            format="jpeg", show_download_button=False,
                                            show_fullscreen_button=False, elem_id="zoom-view")
                            zoom_btn = gr.Button("Reset zoom", size="sm")
                        with gr.Column(scale=2):
                            gr.HTML(STEPS_HTML)
                            click_md = gr.Markdown(self._click_md(None))
                            gr.Markdown(LESION_REMINDER)
                            with gr.Row():
                                severity = gr.Number(label="Severity % of main leaf", step=0.5, value=None, scale=1)
                                slider = gr.Slider(0, 100, value=0, step=0.5, label="…or slide", scale=2)
                            notes = gr.Textbox(label="Notes (ambiguous main leaf, 0% because…, etc.)", lines=2)
                            save_btn = gr.Button("Save & next", variant="primary")
                            with gr.Row():
                                skip_reason = gr.Dropdown(rc.SKIP_REASONS, value=None, label="Skip reason", scale=2)
                                skip_btn = gr.Button("Skip (logged) & next", variant="stop", scale=1)
                            with gr.Row():
                                status = gr.Markdown("No image loaded.")
                                pause_btn = gr.Button("Pause timer", size="sm")
                            gr.Markdown("**Reference diagrams** (exact % of leaf area; synthetic)")
                            with gr.Tabs() as ref_tabs:
                                for style in sad.STYLES:
                                    with gr.Tab(style, id=style):
                                        gr.Image(str(sad.panel_path(style)), show_label=False, interactive=False,
                                                 show_download_button=False)
                    progress_md = gr.Markdown()
                with gr.Tab("Rater training"):
                    gr.HTML(TRAINING_HTML)
                    tr_start = gr.Button("Start new training set (15 leaves)", variant="primary")
                    with gr.Row():
                        with gr.Column(scale=3):
                            tr_info = gr.Markdown()
                            tr_img = gr.Image(label="Training leaf", interactive=False, show_download_button=False,
                                              show_fullscreen_button=False)
                            gr.Markdown(LESION_REMINDER)
                            with gr.Row():
                                tr_num = gr.Number(label="Your severity %", step=0.5, value=None, scale=1)
                                tr_submit = gr.Button("Submit rating", variant="primary", scale=1)
                                tr_next = gr.Button("Next leaf", scale=1)
                            tr_feedback = gr.Markdown()
                        with gr.Column(scale=2):
                            tr_ref = gr.Image(show_label=False, interactive=False, show_download_button=False)
            timer = gr.Timer(5)

            load_out = [st, view, info, click_md, progress_md, severity, slider, notes, skip_reason, ref_tabs,
                        pause_btn, set_dd, counter]
            reset_zoom = dict(fn=None, inputs=None, outputs=None, js=ZOOM_RESET_JS)
            load_btn.click(self.load_next, [set_dd, st], load_out).then(**reset_zoom)
            set_dd.input(lambda s: (self._progress_md(s), self._counter_html(s)), set_dd, [progress_md, counter])
            view.select(self.on_click, st, [st, view, click_md])
            # always_last: the default trigger_mode ("once") drops events fired while one is
            # running, so fast slider moves left the number box on a stale value.
            severity.input(lambda v: v if v is not None else 0, severity, slider, trigger_mode="always_last")
            slider.input(lambda v: v, slider, severity, trigger_mode="always_last")
            save_btn.click(self.save, [rater, severity, slider, notes, st], load_out).then(**reset_zoom)
            skip_btn.click(self.skip, [rater, skip_reason, notes, st], load_out).then(**reset_zoom)
            pause_btn.click(self.toggle_pause, st, [st, pause_btn])
            zoom_btn.click(**reset_zoom)
            timer.tick(self.status_tick, st, status)

            tr_out = [tr_state, tr_img, tr_info, tr_num, tr_feedback, tr_ref]
            tr_start.click(self.train_start, tr_state, tr_out)
            tr_submit.click(self.train_submit, [tr_num, rater, tr_state], tr_out)
            tr_next.click(self.train_next, tr_state, tr_out)

            demo.load(self._progress_md, set_dd, progress_md)
            demo.load(None, None, None, js=ZOOM_JS)
        return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 visual severity rating tool")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--port", type=int, default=7861)
    args = parser.parse_args()
    Rater(load_config(args.config)).build().launch(server_port=args.port)


if __name__ == "__main__":
    main()
