"""Download, verify, and extract PlantSeg v6 from Zenodo.

PlantSeg's own repo README links to an older Zenodo record (14935094, v4) in
the "data/" prep instructions, which can be misleading - the record ID and
even the zip's MD5 change between versions, but they share the same Zenodo
"concept DOI" (10.5281/zenodo.13293890). This script targets record 16665770
(confirmed v6, the latest version as of 2026-10-01) because its MD5
(23385d877bc84bab51b54630055c75b8) matches what was specified for this
project; if PlantSeg publishes a newer version, the MD5 check here will
correctly fail rather than silently accepting a different version.

Usage:
    python -m src.data.download_plantseg --config configs/config.yaml
    python -m src.data.download_plantseg --config configs/config.yaml --force
"""

import argparse
import hashlib
import urllib.request
import zipfile
from pathlib import Path

from tqdm import tqdm

from src.utils.config import load_config

ZENODO_RECORD_ID = "16665770"
ZIP_FILENAME = "Plantseg.zip"
DOWNLOAD_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}/files/{ZIP_FILENAME}/content"
EXPECTED_MD5 = "23385d877bc84bab51b54630055c75b8"


def _md5sum(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_zip(
    dest_dir: Path,
    url: str = DOWNLOAD_URL,
    expected_md5: str = EXPECTED_MD5,
    force: bool = False,
) -> Path:
    """Download the PlantSeg zip into dest_dir, skipping if already present and verified.

    `url` accepts file:// paths too, so this is testable offline.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / ZIP_FILENAME

    if zip_path.exists() and not force:
        if _md5sum(zip_path) == expected_md5:
            print(f"{zip_path} already downloaded and verified, skipping.")
            return zip_path
        print(f"{zip_path} exists but MD5 doesn't match, re-downloading.")

    tmp_path = zip_path.with_suffix(".zip.part")
    with urllib.request.urlopen(url) as response:
        total = int(response.headers.get("content-length", 0))
        with tmp_path.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=ZIP_FILENAME) as bar:
            while chunk := response.read(1 << 20):
                f.write(chunk)
                bar.update(len(chunk))

    actual_md5 = _md5sum(tmp_path)
    if actual_md5 != expected_md5:
        tmp_path.unlink()
        raise ValueError(f"MD5 mismatch: expected {expected_md5}, got {actual_md5}. Downloaded file removed.")

    tmp_path.replace(zip_path)
    return zip_path


def extract_zip(zip_path: Path, dest_dir: Path, force: bool = False) -> Path:
    """Extract the PlantSeg zip into dest_dir, skipping if already extracted."""
    marker = dest_dir / ".extracted"
    if marker.exists() and not force:
        print(f"{dest_dir} already extracted, skipping.")
        return dest_dir

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)

    marker.write_text(f"extracted from {zip_path.name}\n", encoding="utf-8")
    return dest_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract even if already present")
    args = parser.parse_args()

    config = load_config(args.config)
    plantseg_dir = Path(config["data"]["plantseg_dir"])

    zip_path = download_zip(plantseg_dir, force=args.force)
    extract_zip(zip_path, plantseg_dir, force=args.force)
    print(f"PlantSeg ready at {plantseg_dir}")


if __name__ == "__main__":
    main()
