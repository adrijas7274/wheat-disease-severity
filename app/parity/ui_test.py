"""Phone-sized browser test of the built app (app/www served on 127.0.0.1:8080 by `npm run serve`).

Checks: the service worker installs and the page becomes cross-origin isolated (threads), models load, a photo
goes through disease -> tap -> result card, the offline reload works, languages switch (incl. RTL), and the
picker shows every language. Saves screenshots to report/figures/app/.

Usage (repository root): python app/parity/ui_test.py [photo] [x y]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/"
OUT = Path("report/figures/app")


def main() -> None:
    photo = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/examples/wheat_stripe_rust_1.jpg")
    xy = tuple(float(v) for v in sys.argv[2:4]) if len(sys.argv) >= 4 else (0.5, 0.5)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(**p.devices["Pixel 5"], locale="en-IN")
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        page.goto(URL)
        page.wait_for_function("window.crossOriginIsolated === true", timeout=180_000)
        page.wait_for_selector("#loading", state="hidden", timeout=180_000)
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "1_home.png")

        page.set_input_files("#gallery", str(photo))
        page.wait_for_selector("#s-disease:not([hidden])")
        page.screenshot(path=OUT / "2_disease.png")
        page.click("#diseases .choice[data-key='d_stripe_rust']")
        page.wait_for_selector("#s-tap:not([hidden])")
        box = page.locator("#photo").bounding_box()
        page.screenshot(path=OUT / "3_tap.png")
        page.mouse.click(box["x"] + xy[0] * box["width"], box["y"] + xy[1] * box["height"])
        page.wait_for_selector("#s-result:not([hidden])", timeout=180_000)
        page.wait_for_timeout(300)
        page.screenshot(path=OUT / "4_result_en.png", full_page=True)
        report["result_en"] = page.inner_text("#card")

        # same result card in other languages (the card re-renders on a language change), incl. RTL Urdu
        for code, name in [("hi", "5_result_hi.png"), ("ur", "6_result_ur.png"), ("sat", "7_result_sat.png")]:
            page.click("#langBtn")
            page.wait_for_timeout(1000)
            if code == "hi":
                page.screenshot(path=OUT / "8_language_picker.png")
            page.click(f"#langList button[lang='{code}']")
            page.wait_for_timeout(1000)
            page.screenshot(path=OUT / name, full_page=True)
            report[f"dir_{code}"] = page.evaluate("document.documentElement.dir")
            report[f"unverified_note_{code}"] = page.is_visible("#unverified")
        page.click("#again")
        page.click("#aboutBtn")
        report["diag"] = page.inner_text("#diag")
        page.screenshot(path=OUT / "9_about.png", full_page=True)
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
