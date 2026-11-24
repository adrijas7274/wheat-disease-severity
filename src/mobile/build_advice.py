"""Treatment advice table for the app (app/web/advice.json) and its expert review sheet.

Every product row below was transcribed by hand from the official CIBRC list "Major Uses of Pesticides
(Registered under the Insecticides Act, 1968) - Fungicides, upto 30/09/2026" (page numbers given), reading the
rendered PDF pages, not the text layer. Values are copied AS PRINTED (units included only where the document
prints them). Nothing is converted, estimated or filled in: when the source does not give a value (dose per acre,
timing, repeat interval) the field is null and the app does not show it.

The whole table is UNVERIFIED until an agriculture expert checks it.

Usage: python -m src.mobile.build_advice
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

OUT_JSON = Path("app/web/advice.json")
OUT_CSV = Path("report/tables/advice_review.csv")
OUT_MD = Path("report/tables/advice_sources.md")
ACCESSED = "2026-11-23"

SOURCES = {
    "cibrc_mup": {
        "title": "Major Uses of Pesticides (Registered under the Insecticides Act, 1968) - Fungicides (upto 30/09/2026)",
        "issuer": "Central Insecticides Board & Registration Committee (CIB&RC), Directorate of Plant Protection, "
                  "Quarantine & Storage, Ministry of Agriculture & Farmers Welfare, Government of India",
        "url": "https://ppqs.gov.in/sites/default/files/Fungicide%20MUP%20%20as%20on%2030.09.2026.pdf",
        "listing": "https://ppqs.gov.in/divisions/cib-rc/major-uses-of-pesticides",
        "as_on": "2026-09-30",
        "accessed": ACCESSED,
        "note": "The document says it is compiled 'for guidance and not for legal purposes'. Doses are per hectare.",
    },
    "cibrc_banned": {
        "title": "List of pesticides which are banned, refused registration and restricted in use (updated on 31.10.2026)",
        "issuer": "CIB&RC, Directorate of Plant Protection, Quarantine & Storage",
        "url": "https://ppqs.gov.in/sites/default/files/list_of_pesticides_which_are_banned_refused_registration_and_restricted_in_use%20%2831.10.26%29.pdf",
        "listing": "https://ppqs.gov.in/divisions/cib-rc/registered-products",
        "as_on": "2026-10-31",
        "accessed": ACCESSED,
        "note": "Mancozeb is on the restricted list (banned on guava, jowar and tapioca, S.O. 4294(E) of 03.10.2023). "
                "Restricted products are excluded here, so mancozeb (registered on wheat for brown and black rust) "
                "is left out. None of the products kept below is on the list.",
    },
    "ppqs_yr_advisory": {
        "title": "Advisory on yellow rust of wheat (Puccinia striiformis f.sp. tritici) to major wheat growing areas",
        "issuer": "Plant Protection Adviser, Directorate of Plant Protection, Quarantine & Storage, Faridabad",
        "url": "https://ppqs.gov.in/sites/default/files/advisroy_yellow_rust.pdf",
        "as_on": "2022-03 (scanned letter; day not legible)",
        "accessed": ACCESSED,
        "note": "Says 'Fungicides must be used as per label claim approved by the Central Insecticides Board and "
                "Registration Committee' and lists IPM practices; its annexure repeats the CIBRC propiconazole 25% EC "
                "row (125 g a.i., 500gm, 750 L, 30 days).",
    },
}

NOT_REACHED = [
    ("ICAR-IIWBR crop protection page", "https://iiwbr.icar.gov.in/crop-protection/",
     "host did not resolve (DNS) on 2026-11-23; its per-acre doses (e.g. propiconazole 1 ml per litre, 200 ml in "
     "200 L per acre) appear only in news reports, so they are NOT used"),
    ("PPQS wheat rust leaflet", "https://ppqs.gov.in/sites/default/files/wheat_rust-english.pdf", "HTTP 404"),
    ("ICAR rust task-force pages", "https://icar.org.in/en/node/4151", "site under maintenance"),
]


def row(product, disease_as_printed, ai, formulation, water, waiting, page, per_litre=None, note=None):
    """One CIBRC row, values as printed."""
    return {"product": product, "label_disease": disease_as_printed, "ai_per_ha": ai, "formulation_per_ha": formulation,
            "water_l_per_ha": water, "waiting_period_days": waiting, "dose_per_litre": per_litre,
            "dose_per_acre": None, "water_per_acre": None, "timing": None, "repeat_interval": None,
            "source": "cibrc_mup", "page": page, "note": note}


AZ_DIF = row("Azoxystrobin 18.2% + Difenoconazole 11.4% w/w SC", "Rust & Powdery mildew", "0.03% or 0.3 g/l",
             "0.1% or 1 ml / Litre water", "500", "35", 47, per_litre="1 ml / Litre water",
             note="Only wheat row in the list that prints a dose per litre.")
PROPI = row("Propiconazole 25% EC", None, "125gm", "500gm", "750", "30", 24,
            note="Formulation dose printed as '500gm' for a liquid (EC) product; unit to be confirmed by the expert.")
TRIAD = row("Triadimefon 25% WP", None, None, None, "750", "25", 41)
TEBU_SC = row("Tebuconazole 38.39% w/w SC", "Yellow Rust and powdery", "258", "600",
              "375-500 (20 L via drone application)", "5", 38, note="Units of the dose columns not printed.")
KRES = row("Kresoxim-methyl 44.3% SC", "Rust, Leaf blight", "250", "500", "500", "34", 17,
           note="Label says 'Rust' without the type. Units not printed.")
ZINEB = row("Zineb 75% WP", "Rust, blight", "1.125-1.5KG", "1.5-2KG", "750-1000 Lt", None, 42,
            note="No waiting period printed.")
AZ_CYP = row("Azoxystrobin 18.2% w/w + Cyproconazole 7.3% w/w SC", "Rust and Powdery mildew", "0.26% w/v", "1 %",
             "500 (via Knapsack sprayer); 20 (via Drone application)", "50", 46)
AZ_EPO = row("Azoxystrobin 14% + Epoxiconazole 9% SC",
             "Yellow rust (Puccinia striiformis f. sp. tritici), Leaf rust (Puccinia triticina), Powdery mildew "
             "(Erysiphe graminis), Karnal bunt", "(105+67.5) to (140+90)", "750-1000", "500", "35", 48)
AZ_PRO = row("Azoxystrobin 7.1% + Propiconazole 11.9% w/w SE", "Yellow rust (Puccinia striiformis f.sp. Tritici)",
             "56.25+93.75", "750", "500", "45", 50)
AZ_TEB = row("Azoxystrobin 11% + Tebuconazole 18.3% w/w SC", "Yellow Rust", "82.5+137.25", "750", "500", None, 51,
             note="Waiting period printed as '-'.")
PRO_DIF = row("Propiconazole 13.9% w/w + Difenoconazole 13.9% w/w EC", "Rust, Powdery mildew", "105", "350", "500",
              "35", 53)
FLX_PYR = row("Fluxapyroxad 167 g/l + Pyraclostrobin 333 g/l SC", "Rust", "150", "300", "500", "55", 66)
PIC_PRO = row("Picoxystrobin 7.05% + Propiconazole 11.71% SC", "Yellow Rust (Puccinia striiformis sp. tritici)",
              "200", "1000", "500", "52", 78)
PRO_THI = row("Propiconazole 10% + Thiophanate-Methyl 42% WP",
              "Rust-Puccinia graminis tritici (Brown/Leaf/Stem/Stripe); Powdery mildew-Blumeria graminis",
              "100+420", "1000", "500", "49", 81)
PYD_PRO = row("Pydiflumetofen 13.6% w/w + Propiconazole 11.4% w/w SE", "Yellow Rust Powdery Mildew", "165 (90+75)",
              "600", "500", "35", 81)
PYR_EPO = row("Pyraclostrobin 133 g/l + Epoxiconazole 50 g/l SE", "Yellow rust", "137.25", "750", "500", "47", 82)
TEB_SUL = row("Tebuconazole 10% + Sulphur 65% WG", "Powdery Mildew, Leaf Blight and Rust", "(150 + 975) - 1125",
              "1500", "500", "48", 86)
TEB_TRI = row("Tebuconazole 50% + Trifloxystrobin 25% WG", "Yellow rust, powdery mildew", "150+75", "300", "300-500",
              "40", 87)
SULPH = row("Sulphur 80% WG", "Powdery mildew", "2000", "2500", "500", "24", 36, note="Units not printed in the wheat row.")


def _with(r: dict, disease: str, ai, form) -> dict:
    return {**r, "label_disease": disease, "ai_per_ha": ai, "formulation_per_ha": form}


DISEASES = {
    "wheat stripe rust": {
        "chemical_control": "registered",
        "products": [
            AZ_DIF,
            _with(PROPI, "Stripe rust /Yellow Rust (P. striiformis)", "125gm", "500gm"),
            _with(TRIAD, "Brown rust, Yellow rust, Black rust", "250", "1.0"),
            TEBU_SC, KRES, ZINEB, AZ_CYP, AZ_EPO, AZ_PRO, AZ_TEB, PRO_DIF, FLX_PYR, PIC_PRO, PRO_THI, PYD_PRO,
            PYR_EPO, TEB_SUL, TEB_TRI,
        ],
    },
    "wheat leaf rust": {
        "chemical_control": "registered",
        "products": [
            AZ_DIF,
            _with(PROPI, "Leaf rust / Brown Rust (Puccinia recondite F.sp. tritici)", "125gm", "500gm"),
            _with(TRIAD, "Brown rust, Yellow rust, Black rust", "250", "1.0"),
            KRES, ZINEB, AZ_CYP, AZ_EPO, PRO_DIF, FLX_PYR, PRO_THI, TEB_SUL,
        ],
    },
    "wheat powdery mildew": {
        "chemical_control": "registered",
        "products": [
            AZ_DIF, SULPH, TEBU_SC, _with(TRIAD, "Powdery mildew", "65-135 gm", "0.260-0.520"),
            AZ_CYP, AZ_EPO, PRO_DIF, PRO_THI, PYD_PRO, TEB_SUL, TEB_TRI,
        ],
    },
    "wheat septoria blotch": {
        "chemical_control": "none_registered",
        "note": "No wheat Septoria (leaf or glume blotch) entry in the CIBRC fungicide list as on 30.09.2026. The "
                "'Leaf blight' entries are not assumed to cover Septoria.",
        "products": [],
    },
    "wheat bacterial leaf streak (black chaff)": {
        "chemical_control": "none_registered",
        "note": "No wheat bacterial leaf streak / black chaff entry in the CIBRC fungicide list as on 30.09.2026.",
        "products": [],
    },
}

# placeholder severity levels -> action; spraying only where a registered product exists
LEVEL_ACTION = {"none": "no_spray", "low": "watch", "medium": "spray_recommended", "high": "spray_recommended"}
LEVEL_ACTION_NO_PRODUCT = {"none": "no_spray", "low": "watch", "medium": "ask_expert", "high": "ask_expert"}

# --------------------------------------------------------------------------------------------- conversions
# Adrija's decision (2026-11-23): show per hectare (official) plus per acre and per 15-litre tank, the last two
# labelled "converted from the official figure". Conversions are plain arithmetic on the printed numbers:
#   per acre = per hectare x 0.40468564224 (1 acre = 0.40468564224 ha exactly, international acre)
#   per tank = printed dose per litre x 15, else (formulation per ha / water L per ha) x 15
# Nothing is converted when the official cell prints no unit (the list's column heading "(g/ml)" does not hold
# for every row: e.g. triadimefon "0.260-0.520" can only be kg), or, for the tank, when both dose and water are
# ranges (which dose goes with which water volume is not stated).
HA_PER_ACRE = 0.40468564224
TANK_L = 15

UNITS = {"gm": "g", "g": "g", "kg": "kg", "ml": "ml", "l": "L", "lit": "L", "lt": "L", "ltr": "L"}
_AMOUNT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:(?:-|to|–)\s*(\d+(?:\.\d+)?))?\s*([A-Za-z]+)\b")
_WATER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:(?:-|to|–)\s*(\d+(?:\.\d+)?))?")


def parse_amount(text):
    """'500gm' -> (500, 500, 'g'); '1.5-2KG' -> (1.5, 2, 'kg'); '1 ml / Litre water' -> (1, 1, 'ml').
    None when the cell has no plain number or range followed by a printed unit."""
    if not text:
        return None
    m = _AMOUNT.match(str(text))
    if not m or m.group(3).lower() not in UNITS:
        return None
    lo = float(m.group(1))
    return lo, float(m.group(2)) if m.group(2) else lo, UNITS[m.group(3).lower()]


def parse_water(text):
    """Water L/ha: the first number or range ('500', '750-1000 Lt', '375-500 (20 L via drone)') -> (lo, hi)."""
    if not text:
        return None
    m = _WATER.match(str(text))
    if not m:
        return None
    lo = float(m.group(1))
    return lo, float(m.group(2)) if m.group(2) else lo


def fmt(lo, hi, unit, digits):
    """Display text, rounded ('202.3 g', '0.61-0.81 kg'); the exact numbers are stored beside it."""
    def r(x):
        return f"{round(x, digits):.{digits}f}".rstrip("0").rstrip(".")
    return f"{r(lo)} {unit}" if lo == hi else f"{r(lo)}-{r(hi)} {unit}"


def _digits(unit):
    return 2 if unit in ("kg", "L") else 1


def conversions(p):
    """Per acre (dose and water) and per 15-litre tank, with the reason when something is not converted."""
    out = {"per_acre": None, "water_per_acre": None, "per_tank": None, "not_converted": []}
    water = parse_water(p["water_l_per_ha"])
    per_litre = parse_amount(p["dose_per_litre"])
    dose = parse_amount(p["formulation_per_ha"])
    if dose is None and per_litre is not None and water is not None and water[0] == water[1]:
        dose = (per_litre[0] * water[0], per_litre[1] * water[0], per_litre[2])
        out["per_ha_from"] = "dose per litre x water per hectare (both official)"
    if dose is not None:
        lo, hi = dose[0] * HA_PER_ACRE, dose[1] * HA_PER_ACRE
        out["per_acre"] = {"lo": lo, "hi": hi, "unit": dose[2], "text": fmt(lo, hi, dose[2], _digits(dose[2]))}
    else:
        out["not_converted"].append("dose: no unit printed in the official cell")
    if water is not None:
        lo, hi = water[0] * HA_PER_ACRE, water[1] * HA_PER_ACRE
        out["water_per_acre"] = {"lo": lo, "hi": hi, "unit": "L", "text": fmt(lo, hi, "L", 0)}
    if per_litre is not None:
        lo, hi = per_litre[0] * TANK_L, per_litre[1] * TANK_L
        out["per_tank"] = {"lo": lo, "hi": hi, "unit": per_litre[2], "text": fmt(lo, hi, per_litre[2], 1)}
    elif dose is not None and water is not None:
        if dose[0] != dose[1] and water[0] != water[1]:
            out["not_converted"].append("tank: both dose and water are ranges")
        else:
            lo, hi = sorted([dose[0] / water[1] * TANK_L, dose[1] / water[0] * TANK_L])
            out["per_tank"] = {"lo": lo, "hi": hi, "unit": dose[2], "text": fmt(lo, hi, dose[2], _digits(dose[2]) + 1)}
    return out


# ---------------------------------------------------------------------------------------- options shown
# Adrija's decision: no single default; show up to 3 registered options per disease, unranked. Which 3 is a
# completeness rule, not a ranking: rows whose dose has a printed unit (so every conversion exists) first, then
# rows with a printed waiting period, then single-ingredient products, then the order of the official list.
# They are displayed in the order of the official list. The expert marks a default in the review sheet.
N_OPTIONS = 3


def _completeness(p):
    c = conversions(p)
    doubtful = 1 if "to be confirmed" in (p.get("note") or "") else 0  # e.g. propiconazole '500gm' for a liquid
    return (doubtful, 0 if c["per_acre"] else 1, 0 if c["per_tank"] else 1, 0 if p["waiting_period_days"] else 1,
            0 if "+" not in p["product"] else 1)


def pick_options(products):
    """Indices of the (up to) 3 products the app shows, in official-list order."""
    order = sorted(range(len(products)), key=lambda i: (*_completeness(products[i]), products[i]["page"], i))
    return sorted(order[:N_OPTIONS], key=lambda i: (products[i]["page"], i))


def build() -> dict:
    """The advice table."""
    diseases = {}
    for name, d in DISEASES.items():
        levels = LEVEL_ACTION if d["products"] else LEVEL_ACTION_NO_PRODUCT
        products = [{**p, "converted": conversions(p)} for p in d["products"]]
        diseases[name] = {**d, "products": products, "levels": levels,
                          "options": pick_options(d["products"]) if products else []}
    return {
        "status": "unverified",
        "verified_by": None,
        "about": "Treatment advice per disease and placeholder severity level. Official values are copied as printed; "
                 "per-acre and per-15-litre-tank values are arithmetic conversions of them, labelled as converted. "
                 "Nothing is estimated, and the dose never depends on the severity percentage. 'options' are up to 3 "
                 "registered products shown in the app, unranked (selection rule in src/mobile/build_advice.py). "
                 "Timing and repeat interval are left out until an official advisory gives them. "
                 "UNVERIFIED: no agriculture expert has checked this table.",
        "kisan_call_centre": "1800-180-1551",
        "conversion": {"ha_per_acre": HA_PER_ACRE, "tank_litres": TANK_L},
        "sources": SOURCES,
        "sources_not_reached": [{"name": n, "url": u, "why": w} for n, u, w in NOT_REACHED],
        "excluded": [{"product": "Mancozeb 75% WP", "why": "restricted in use (CIBRC list, 31.10.2026)",
                      "source": "cibrc_banned"}],
        "diseases": diseases,
    }


def review_rows(advice: dict) -> list[list[str]]:
    """One row per disease x product (or one row for a disease with none), sources beside each row."""
    header = ["disease", "chemical control", "shown in app (unranked)", "product (as printed)", "disease on label",
              "a.i. per ha", "formulation per ha (official)", "water L per ha (official)", "waiting period (days)",
              "dose per litre (official)", "per acre (converted)", "water per acre (converted)",
              "per 15-L tank (converted)", "not converted because", "timing", "repeat interval", "source", "page",
              "URL", "source note", "EXPERT: correct? (yes/no)", "EXPERT: corrections",
              "EXPERT: default for this disease (mark one)", "EXPERT: name / date"]
    out = [header]
    for name, d in advice["diseases"].items():
        if not d["products"]:
            out.append([name, d["chemical_control"]] + [""] * 14
                       + ["cibrc_mup", "", SOURCES["cibrc_mup"]["url"], d.get("note", ""), "", "", "", ""])
            continue
        for i, p in enumerate(d["products"]):
            def v(k):
                return "" if p[k] is None else str(p[k])
            c = p["converted"]

            def t(k):
                return c[k]["text"] if c[k] else ""
            out.append([name, d["chemical_control"], "yes" if i in d["options"] else "", p["product"],
                        v("label_disease"), v("ai_per_ha"), v("formulation_per_ha"), v("water_l_per_ha"),
                        v("waiting_period_days"), v("dose_per_litre"), t("per_acre"), t("water_per_acre"),
                        t("per_tank"), "; ".join(c["not_converted"]), "not in a reached official source",
                        "not in a reached official source", p["source"], str(p["page"]),
                        SOURCES[p["source"]]["url"], v("note"), "", "", "", ""])
    return out


def sources_md(advice: dict) -> str:
    """Markdown list of sources and the options the app shows, for review."""
    lines = ["# Treatment advice: sources (UNVERIFIED until an agriculture expert checks it)", ""]
    for key, s in advice["sources"].items():
        lines += [f"- **{key}**: {s['title']}. {s['issuer']}. As on {s['as_on']}, accessed {s['accessed']}.",
                  f"  {s['url']}", f"  {s['note']}"]
    lines += ["", "Not reachable or not used:"]
    lines += [f"- {s['name']}: {s['url']} ({s['why']})" for s in advice["sources_not_reached"]]
    lines += ["", "Options shown in the app (unranked, in the order of the official list). Official: per ha, water, "
              "waiting period. Converted from the official figure: per acre, per 15-L tank.", "",
              "| disease | product | per ha (official) | water L/ha (official) | waiting days (official) | "
              "per acre (converted) | per 15-L tank (converted) | page |", "|---|---|---|---|---|---|---|---:|"]
    for name, d in advice["diseases"].items():
        if not d["products"]:
            lines.append(f"| {name} | none registered | - | - | - | - | - | - |")
            continue
        for i in d["options"]:
            p = d["products"][i]
            c = p["converted"]
            lines.append(f"| {name} | {p['product']} | {p['formulation_per_ha']} | {p['water_l_per_ha']} | "
                         f"{p['waiting_period_days'] or 'not printed'} | "
                         f"{c['per_acre']['text'] if c['per_acre'] else 'not converted'} | "
                         f"{c['per_tank']['text'] if c['per_tank'] else 'not converted'} | {p['page']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Write advice.json, the review CSV and the sources note."""
    advice = build()
    OUT_JSON.write_text(json.dumps(advice, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(review_rows(advice))
    OUT_MD.write_text(sources_md(advice), encoding="utf-8")
    n = sum(len(d["products"]) for d in advice["diseases"].values())
    print(f"wrote {OUT_JSON}, {OUT_CSV} ({n} product rows) and {OUT_MD}")


if __name__ == "__main__":
    main()
