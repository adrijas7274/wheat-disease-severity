"""Phone-sized browser test of the built app (app/www served on 127.0.0.1:8080 by `npm run serve`).

Walks every screen on a fresh phone: language picker (first start) -> how-to -> home -> live camera (Chromium's
fake camera) -> gallery photo -> disease -> tap -> scanning -> result (en, hi, RTL ur, sat) -> history -> about,
then reloads offline. Checks the service worker, cross-origin isolation (threads), the advice card and the call
button, and saves a screenshot of every screen to report/figures/app/.

Usage (repository root): python app/parity/ui_test.py [photo] [x y]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
OUT = Path("report/figures/app")


def shot(page, name: str, full: bool = False) -> None:
    page.wait_for_timeout(350)  # let the enter animation finish
    page.screenshot(path=OUT / name, full_page=full)


def main() -> None:
    photo = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/examples/wheat_stripe_rust_1.jpg")
    xy = tuple(float(v) for v in sys.argv[2:4]) if len(sys.argv) >= 4 else (0.5, 0.5)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
        ctx = browser.new_context(**p.devices["Pixel 5"], locale="en-IN", permissions=["camera"])
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        page.goto(URL)
        page.wait_for_function("window.crossOriginIsolated === true", timeout=180_000)
        page.wait_for_selector("#loading", state="hidden", timeout=180_000)

        # first start: language picker, then the how-to
        page.wait_for_selector("#s-lang:not([hidden])")
        page.wait_for_timeout(1500)  # script fonts
        shot(page, "01_language.png")
        report["language_tiles"] = page.locator(".langTile").count()
        page.click(".langTile[lang='en']")
        page.wait_for_selector("#s-howto:not([hidden])")
        shot(page, "02_howto.png", full=True)
        page.click("#howtoDone")
        page.wait_for_selector("#s-home:not([hidden])")
        shot(page, "03_home.png")

        # live camera with the leaf guide and hints (fake camera)
        page.click("#cameraBtn")
        page.wait_for_selector("#s-camera:not([hidden])")
        page.wait_for_timeout(1500)
        report["camera_hint"] = page.inner_text("#camHint")
        shot(page, "04_camera.png")
        page.click("#backBtn")
        page.wait_for_selector("#s-home:not([hidden])")

        page.set_input_files("#gallery", str(photo))
        page.wait_for_selector("#s-disease:not([hidden])")
        shot(page, "05_disease.png")
        page.click("#diseases .choice[data-key='d_stripe_rust']")
        page.wait_for_selector("#s-tap:not([hidden])")
        shot(page, "06_tap.png")
        box = page.locator("#photo").bounding_box()
        page.mouse.click(box["x"] + xy[0] * box["width"], box["y"] + xy[1] * box["height"])
        page.wait_for_timeout(500)
        shot(page, "07_scanning.png")
        page.wait_for_selector("#leafGlow:not([hidden])", timeout=180_000)
        page.screenshot(path=OUT / "08_leaf_highlight.png")
        page.wait_for_selector("#s-result:not([hidden])", timeout=180_000)
        page.wait_for_timeout(1200)  # gauge animation
        shot(page, "09_result_en.png", full=True)
        report["result_en"] = page.inner_text("#card")
        report["advice_en"] = page.inner_text("#advice") if page.is_visible("#advice") else None
        report["options_shown"] = page.locator("#advList .option").count()
        report["call_button"] = page.get_attribute("#callKcc", "href")
        page.click("#viewPhoto")
        page.locator("#overlay").screenshot(path=OUT / "10_result_photo_view.png")
        page.click("#viewDisease")

        # same result card in other languages, incl. RTL Urdu and Ol Chiki
        for code, name in [("hi", "11_result_hi.png"), ("ur", "12_result_ur.png"), ("sat", "13_result_sat.png")]:
            page.click("#langBtn")
            page.wait_for_selector("#s-lang:not([hidden])")
            page.click(f".langTile[lang='{code}']")
            page.wait_for_selector("#s-result:not([hidden])")
            page.wait_for_timeout(1200)
            shot(page, name, full=True)
            report[f"dir_{code}"] = page.evaluate("document.documentElement.dir")
            report[f"unverified_note_{code}"] = page.is_visible("#unverified")
        page.click("#langBtn")
        page.click(".langTile[lang='en']")
        page.wait_for_selector("#s-result:not([hidden])")

        page.click("#again")
        page.click("#historyBtn")
        page.wait_for_selector("#s-history:not([hidden])")
        report["history_items"] = page.locator(".histItem").count()
        shot(page, "14_history.png")
        page.click("#backBtn")
        page.click("#aboutBtn")
        report["diag"] = page.inner_text("#diag")
        shot(page, "15_about.png", full=True)
        page.click("#aboutBack")

        # offline: reload with the network off, the app must still start and load the models
        ctx.set_offline(True)
        page.reload()
        page.wait_for_selector("#loading", state="hidden", timeout=180_000)
        report["offline_start"] = page.evaluate("!document.querySelector('#s-home').hidden")
        ctx.set_offline(False)
        report["console"] = [l for l in logs if "error" in l.lower()][:20]
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
