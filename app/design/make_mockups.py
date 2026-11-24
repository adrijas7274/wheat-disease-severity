"""Three design directions for the home and result screens, rendered to PNG for review.

Static mockups (no pipeline), using the design tokens in tokens.css and real numbers from the browser test of the
stripe-rust example (10.5%, medium) and the advice table. Output: report/figures/app/mockups/.
Usage (repository root): python app/design/make_mockups.py
"""
from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report/figures/app/mockups"
TOKENS = (ROOT / "app/web/css/tokens.css").read_text(encoding="utf-8")
PHOTO = "data:image/jpeg;base64," + base64.b64encode((ROOT / "demo/examples/wheat_stripe_rust_1.jpg").read_bytes()).decode()

WHEAT = """<svg viewBox="0 0 120 120" aria-hidden="true" style="width:100%;height:100%"><g fill="none" stroke-linecap="round">
<path d="M60 118V40" stroke="#8A6500" stroke-width="4"/>
<g fill="#E0B23C" stroke="#8A6500" stroke-width="1.5">
<ellipse cx="52" cy="46" rx="6" ry="11" transform="rotate(-25 52 46)"/><ellipse cx="68" cy="46" rx="6" ry="11" transform="rotate(25 68 46)"/>
<ellipse cx="51" cy="64" rx="6" ry="11" transform="rotate(-25 51 64)"/><ellipse cx="69" cy="64" rx="6" ry="11" transform="rotate(25 69 64)"/>
<ellipse cx="52" cy="82" rx="6" ry="11" transform="rotate(-25 52 82)"/><ellipse cx="68" cy="82" rx="6" ry="11" transform="rotate(25 68 82)"/>
<ellipse cx="60" cy="30" rx="6" ry="12"/></g>
<path d="M60 100c-14-4-24-12-30-26 12 2 24 10 30 26zm0 0c14-4 24-12 30-26-12 2-24 10-30 26z" fill="#2F6B2F"/></g></svg>"""

ICON = {
    "camera": '<svg viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="4"/></svg>',
    "gallery": '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m3 17 5-5 4 4 3-3 6 6"/><circle cx="16" cy="9" r="1.6"/></svg>',
    "howto": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5V14M12 17v.5"/></svg>',
    "history": '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>',
    "globe": '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></svg>',
    "speaker": '<svg viewBox="0 0 24 24"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>',
    "phone": '<svg viewBox="0 0 24 24"><path d="M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 5a2 2 0 0 1 2-2"/></svg>',
    "spray": '<svg viewBox="0 0 24 24"><path d="M9 9h6v12H9zM10 9V6h4v3M14 6h3M17 4v4M19 5h2M19 7h2M8 13h8"/></svg>',
    "warn": '<svg viewBox="0 0 24 24"><path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/></svg>',
}

BASE = """
* { box-sizing: border-box; }
body { margin: 0; background: var(--cream); color: var(--ink); font: var(--fs-body)/var(--lh) "Noto Sans", system-ui, sans-serif; }
svg { width: 28px; height: 28px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.btn { display: flex; align-items: center; justify-content: center; gap: 14px; min-height: 72px; border-radius: var(--r-md);
  font-size: 22px; font-weight: 700; border: 2px solid var(--line); background: var(--card); color: var(--ink); box-shadow: var(--shadow-1); }
.btn.primary { background: var(--green-700); border-color: var(--green-700); color: #fff; }
.btn.gold { background: var(--gold-400); border-color: var(--gold-400); color: var(--ink); }
.btn svg { width: 34px; height: 34px; }
.pill { display: inline-flex; align-items: center; gap: 6px; min-height: 48px; padding: 0 14px; border-radius: var(--r-pill);
  border: 2px solid currentColor; font-size: 17px; font-weight: 600; }
.gauge { position: relative; width: 168px; height: 168px; flex: none; }
.gauge .num { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; color: var(--ink); }
.gauge .num b { font-size: 40px; line-height: 1; display: block; }
.gauge .num small { font-size: 16px; color: var(--muted); }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: var(--r-pill); font-weight: 800; font-size: 20px; color: #fff; }
.adv { background: var(--card); border-radius: var(--r-md); box-shadow: var(--shadow-1); padding: 16px; }
.adv h3 { margin: 0 0 10px; font-size: 20px; display: flex; align-items: center; gap: 8px; }
.adv dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; margin: 0; font-size: 18px; }
.adv dt { color: var(--muted); } .adv dd { margin: 0; font-weight: 700; }
.warnbox { display: flex; gap: 8px; align-items: flex-start; background: var(--gold-100); color: #4A3600; border-radius: var(--r-sm);
  padding: 10px 12px; font-size: 18px; margin-bottom: 12px; }
.warnbox svg { width: 22px; height: 22px; }
.seg { display: inline-flex; border: 2px solid var(--green-700); border-radius: var(--r-pill); overflow: hidden; }
.seg span { min-height: 48px; display: grid; place-items: center; padding: 0 16px; font-weight: 700; font-size: 17px; color: var(--green-700); }
.seg span.on { background: var(--green-700); color: #fff; }
.note { color: var(--muted); font-size: 18px; margin: 0; }
"""


def gauge(pct: float, colour: str, size: int = 168, ring: int = 16) -> str:
    """Circular severity gauge: arc length = percentage, ticks at the placeholder 5% and 20% thresholds."""
    import math
    r = (size - ring) / 2
    c = 2 * math.pi * r
    ticks = ""
    for t in (5, 20):
        a = -math.pi / 2 + 2 * math.pi * t / 100
        x1, y1 = size / 2 + (r - ring / 2 - 2) * math.cos(a), size / 2 + (r - ring / 2 - 2) * math.sin(a)
        x2, y2 = size / 2 + (r + ring / 2 + 2) * math.cos(a), size / 2 + (r + ring / 2 + 2) * math.sin(a)
        ticks += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#1B2118" stroke-width="2"/>'
    return (f'<div class="gauge" style="width:{size}px;height:{size}px"><svg viewBox="0 0 {size} {size}" style="width:{size}px;height:{size}px">'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" stroke="#ECE5CF" stroke-width="{ring}"/>'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" stroke="{colour}" stroke-width="{ring}" stroke-linecap="round" '
            f'stroke-dasharray="{c * pct / 100:.1f} {c:.1f}" transform="rotate(-90 {size/2} {size/2})"/>{ticks}</svg>'
            f'<div class="num"><div><b>10.5%</b><small>of the leaf</small></div></div></div>')


ADVICE = f"""<div class="adv"><h3>{ICON['spray']} Spray advice</h3>
<div class="warnbox">{ICON['warn']}<span>Advice not yet checked by an agriculture expert. Confirm with Kisan Call Centre 1800-180-1551 or your local KVK.</span></div>
<dl><dt>Product</dt><dd>Azoxystrobin 18.2% + Difenoconazole 11.4% w/w SC</dd>
<dt>Per litre</dt><dd>1 ml / Litre water</dd><dt>Water / ha</dt><dd>500 L</dd></dl>
<p class="note" style="margin-top:8px">Do not harvest within 35 days of the last spray. Read and follow the label.</p>
<p class="note">Source: CIBRC Major Uses of Pesticides, 30.09.2026, p. 47</p></div>"""
CALL = f'<div class="btn" style="background:#0B5FA5;border-color:#0B5FA5;color:#fff">{ICON["phone"]}<span>Call Kisan Call Centre<br><small style="font-size:18px">1800-180-1551</small></span></div>'

SCREENS = {
    # A: "Harvest card" - cream, illustration hero, gauge inside one big result card
    "A_home": f"""<div style="padding:16px;display:flex;flex-direction:column;gap:14px;min-height:844px">
<div style="display:flex;align-items:center;justify-content:space-between"><b style="font-size:22px;color:var(--green-900)">Wheat leaf check</b>
<span class="pill" style="color:var(--green-900)">{ICON['globe']} हिन्दी</span></div>
<div style="background:linear-gradient(160deg,var(--gold-100),#FFF);border-radius:var(--r-lg);padding:20px;box-shadow:var(--shadow-1);display:flex;gap:12px;align-items:center">
<div style="width:110px;height:110px">{WHEAT}</div><div><div style="font-size:26px;font-weight:800;color:var(--green-900);line-height:1.2">Check your wheat leaf</div>
<p class="note" style="margin-top:6px">Works without internet</p></div></div>
<div class="btn primary" style="min-height:84px;font-size:24px">{ICON['camera']} Take photo</div>
<div class="btn">{ICON['gallery']} Choose photo</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px"><div class="btn" style="font-size:19px">{ICON['howto']} How to</div><div class="btn" style="font-size:19px">{ICON['history']} My scans</div></div>
<p class="note" style="margin-top:auto">This app only helps you decide. Ask an agriculture expert before spraying.</p></div>""",
    "A_result": f"""<div style="padding:16px;display:flex;flex-direction:column;gap:14px">
<div style="background:var(--card);border-radius:var(--r-lg);box-shadow:var(--shadow-2);padding:18px;border-top:10px solid var(--o-treat)">
<div style="display:flex;gap:16px;align-items:center">{gauge(10.5, '#A34700')}
<div><span class="chip" style="background:var(--o-treat)">{ICON['spray']} Medium</span>
<p style="font-size:22px;font-weight:800;margin:10px 0 0">Disease is present. Treat the crop.</p></div></div>
<div class="btn" style="margin-top:14px;background:var(--o-treat);border-color:var(--o-treat);color:#fff">{ICON['speaker']} Listen</div></div>
<div style="position:relative"><img src="{PHOTO}" style="width:100%;height:190px;object-fit:cover;border-radius:var(--r-md)">
<div class="seg" style="position:absolute;left:10px;bottom:10px;background:#fff"><span>Photo</span><span class="on">Disease</span></div></div>
{ADVICE}{CALL}</div>""",

    # B: "Colour band" - full-width outcome band on top, tiles home
    "B_home": f"""<div style="min-height:844px;display:flex;flex-direction:column">
<div style="background:var(--green-900);color:#fff;padding:22px 16px 60px;border-radius:0 0 var(--r-lg) var(--r-lg)">
<div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:22px">Wheat leaf check</b><span class="pill">{ICON['globe']} English</span></div>
<div style="display:flex;align-items:center;gap:8px;margin-top:18px"><div style="width:84px;height:84px;background:var(--gold-100);border-radius:50%;padding:6px">{WHEAT}</div>
<div style="font-size:24px;font-weight:800;line-height:1.25">Is my wheat sick?<br><span style="color:var(--gold-400)">Take one photo.</span></div></div></div>
<div style="margin:-40px 16px 0;display:grid;grid-template-columns:1fr 1fr;gap:12px">
<div class="btn primary" style="flex-direction:column;min-height:150px;font-size:21px;background:var(--gold-400);border-color:var(--gold-400);color:var(--ink)">{ICON['camera'].replace('<svg', '<svg style="width:48px;height:48px"')} Take photo</div>
<div class="btn" style="flex-direction:column;min-height:150px;font-size:21px">{ICON['gallery'].replace('<svg', '<svg style="width:48px;height:48px"')} Gallery</div>
<div class="btn" style="flex-direction:column;min-height:120px;font-size:19px">{ICON['howto']} How to</div>
<div class="btn" style="flex-direction:column;min-height:120px;font-size:19px">{ICON['history']} My scans</div></div>
<p class="note" style="margin:auto 16px 16px">This app only helps you decide. Ask an agriculture expert before spraying.</p></div>""",
    "B_result": f"""<div style="display:flex;flex-direction:column;gap:14px;padding-bottom:16px">
<div style="background:var(--o-treat);color:#fff;padding:20px 16px 24px;border-radius:0 0 var(--r-lg) var(--r-lg)">
<div style="display:flex;align-items:center;gap:16px"><div style="background:#fff;border-radius:50%;padding:6px">{gauge(10.5, '#A34700', 140, 14)}</div>
<div><div style="font-size:30px;font-weight:900;display:flex;align-items:center;gap:8px">{ICON['spray']} MEDIUM</div>
<p style="font-size:21px;font-weight:700;margin:6px 0 0">Disease is present. Treat the crop.</p></div></div>
<div style="display:flex;gap:10px;margin-top:14px"><div class="btn" style="flex:1;min-height:60px;background:rgba(255,255,255,.15);border-color:#fff;color:#fff">{ICON['speaker']} Listen</div>
<div class="btn" style="flex:1;min-height:60px;background:#fff;border-color:#fff;color:#0B5FA5">{ICON['phone']} 1800-180-1551</div></div></div>
<div style="padding:0 16px;display:flex;flex-direction:column;gap:14px">
<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><img src="{PHOTO}" style="width:100%;height:150px;object-fit:cover;border-radius:var(--r-sm)"><p class="note">Before</p></div>
<div><img src="{PHOTO}" style="width:100%;height:150px;object-fit:cover;border-radius:var(--r-sm);filter:saturate(1.8) hue-rotate(-30deg)"><p class="note">Disease marked</p></div></div>
{ADVICE}</div></div>""",

    # C: "Quiet field" - white cards on cream, linear level scale + gauge, big single action
    "C_home": f"""<div style="padding:16px;display:flex;flex-direction:column;gap:16px;min-height:844px">
<div style="display:flex;justify-content:space-between;align-items:center"><span class="pill" style="color:var(--muted)">{ICON['history']} My scans</span>
<span class="pill" style="color:var(--muted)">{ICON['globe']} English</span></div>
<div style="text-align:center;margin-top:20px"><div style="width:150px;height:150px;margin:0 auto">{WHEAT}</div>
<div style="font-size:30px;font-weight:800;color:var(--green-900)">Wheat leaf check</div><p class="note" style="font-size:18px">Photo of one sick leaf, in daylight</p></div>
<div style="margin:12px auto;width:210px;height:210px;border-radius:50%;background:var(--green-700);color:#fff;display:grid;place-items:center;box-shadow:var(--shadow-2);text-align:center;font-size:24px;font-weight:800">
<div>{ICON['camera'].replace('<svg', '<svg style="width:64px;height:64px"')}<br>Take photo</div></div>
<div class="btn">{ICON['gallery']} Choose from gallery</div>
<div class="btn" style="background:var(--gold-100);border-color:var(--gold-100)">{ICON['howto']} How to take a good photo</div>
<p class="note" style="margin-top:auto">This app only helps you decide. Ask an agriculture expert before spraying.</p></div>""",
    "C_result": f"""<div style="padding:16px;display:flex;flex-direction:column;gap:14px">
<div style="background:var(--card);border-radius:var(--r-lg);box-shadow:var(--shadow-1);padding:18px;text-align:center">
<div style="display:flex;justify-content:center">{gauge(10.5, '#A34700', 190, 18)}</div>
<div style="display:flex;gap:6px;justify-content:center;margin-top:12px">
<span style="padding:6px 10px;border-radius:8px;background:#E9F2EC;color:var(--o-no_action);font-weight:700">None</span>
<span style="padding:6px 10px;border-radius:8px;background:#E7EFF8;color:var(--o-monitor);font-weight:700">Low</span>
<span style="padding:6px 10px;border-radius:8px;background:var(--o-treat);color:#fff;font-weight:900;outline:3px solid var(--ink)">▼ Medium</span>
<span style="padding:6px 10px;border-radius:8px;background:#F8E9E8;color:var(--o-treat_urgently);font-weight:700">High</span></div>
<p style="font-size:22px;font-weight:800;margin:12px 0 0;display:flex;gap:8px;justify-content:center;align-items:center;color:var(--o-treat)">{ICON['spray']} Treat the crop</p>
<div style="display:flex;gap:10px;margin-top:12px;justify-content:center"><div class="seg"><span>Photo</span><span class="on">Disease</span></div>
<div class="btn" style="min-height:52px;padding:0 16px;font-size:18px">{ICON['speaker']} Listen</div></div></div>
{ADVICE}{CALL}</div>""",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        for name, body in SCREENS.items():
            html = (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" '
                    f'href="file:///{(ROOT / "app/www/fonts/latin.css").as_posix()}"><style>{TOKENS}{BASE}</style></head><body>{body}</body></html>')
            page.set_content(html)
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
        b.close()
    print("wrote", len(SCREENS), "mockups to", OUT)


if __name__ == "__main__":
    main()
