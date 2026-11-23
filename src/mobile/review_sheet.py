"""Translation review sheet for native speakers, built from app/web/strings.json.

One row per phrase, the English meaning first, then one column per language (header shows the
language name, its own-script name and the status: machine_draft or verified). Writes
report/tables/translation_review.csv (UTF-8) and translation_review_howto.md.

Usage: python -m src.mobile.review_sheet
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

STRINGS = Path("app/web/strings.json")
OUT_CSV = Path("report/tables/translation_review.csv")

NOTES = {
    "d_stripe_rust": "Disease button. Use the name farmers in your area use, then a short visual hint.",
    "d_leaf_rust": "Disease button (brown rust). Local name + visual hint.",
    "d_powdery_mildew": "Disease button. Local name + visual hint.",
    "d_septoria": "Disease button. Usually no local name; a transliteration is fine.",
    "d_black_chaff": "Disease button (bacterial leaf streak). Local name if one exists.",
    "severity": "{pct} is replaced by a number, e.g. 12.5. Keep {pct} exactly as written.",
    "placeholder": "Shown under every result: the thresholds are not yet checked by agronomists.",
    "unverified": "Small note shown while this language is not yet checked by a native speaker.",
    "no_voice": "Shown when the phone has no text-to-speech voice for this language.",
    "listen": "Button that reads the result aloud.",
    "credits": "Button that opens the about / credits page.",
}


def load(path: Path = STRINGS) -> dict:
    """Read the strings file."""
    return json.loads(path.read_text(encoding="utf-8"))


def rows(data: dict) -> tuple[list[str], list[list[str]]]:
    """Header and one row per phrase key: key, English, note, then every language in order."""
    langs = [c for c in data["order"] if c != "en"]
    meta = data["languages"]
    header = ["key", "English (meaning)", "note for translator"] + [
        f"{meta[c]['name']} / {meta[c]['native']} [{c}] ({meta[c]['status']}, draft confidence: {meta[c]['draft_confidence']})"
        for c in langs]
    body = [[k, v, NOTES.get(k, "")] + [meta[c]["strings"][k] for c in langs]
            for k, v in meta["en"]["strings"].items()]
    return header, body


HELP = """# Translation review: how to help

Open `translation_review.csv` in Google Sheets or Excel (it is UTF-8; in Excel use Data > From Text/CSV if the
letters look wrong). One reviewer per language is enough.

1. Find your language's column. Column B is the English meaning, column C a note for the translator.
2. If a phrase is right, leave it. If not, type the corrected phrase in the same cell.
3. Keep phrases short and simple: many users read little. Use words a farmer would say.
4. Keep `{pct}` exactly as written (it becomes a number).
5. Send the file back with the language you checked (and your name for the credits, if you want).

Every column is a machine draft until a native speaker checks it. None is verified yet.
"""


def write(data: dict, csv_path: Path = OUT_CSV) -> None:
    """Write the review CSV (UTF-8 with BOM so Excel detects it) and the how-to note next to it."""
    header, body = rows(data)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([header] + body)
    csv_path.with_name("translation_review_howto.md").write_text(HELP, encoding="utf-8")


def main() -> None:
    """Build the review sheet."""
    data = load()
    write(data)
    print(f"wrote {OUT_CSV}: {len(data['languages']['en']['strings'])} phrases x {len(data['order']) - 1} languages")


if __name__ == "__main__":
    main()
