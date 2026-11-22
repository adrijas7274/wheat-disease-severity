import hashlib
import zipfile
from pathlib import Path

import pytest

from src.data.download_plantseg import download_zip, extract_zip


def _make_zip(path: Path, content: bytes = b"hello plantseg") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("inner.txt", content)


def test_download_zip_fetches_and_verifies(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    _make_zip(source)
    expected_md5 = hashlib.md5(source.read_bytes()).hexdigest()

    dest_dir = tmp_path / "dest"
    result = download_zip(dest_dir, url=source.resolve().as_uri(), expected_md5=expected_md5)

    assert result == dest_dir / "Plantseg.zip"
    assert result.exists()


def test_download_zip_rejects_md5_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    _make_zip(source)

    dest_dir = tmp_path / "dest"
    with pytest.raises(ValueError, match="MD5 mismatch"):
        download_zip(dest_dir, url=source.resolve().as_uri(), expected_md5="0" * 32)

    assert not (dest_dir / "Plantseg.zip").exists()


def test_download_zip_skips_if_already_verified(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    _make_zip(source)
    expected_md5 = hashlib.md5(source.read_bytes()).hexdigest()

    dest_dir = tmp_path / "dest"
    first = download_zip(dest_dir, url=source.resolve().as_uri(), expected_md5=expected_md5)
    mtime_before = first.stat().st_mtime_ns

    second = download_zip(dest_dir, url="file:///should-not-be-fetched", expected_md5=expected_md5)

    assert second.stat().st_mtime_ns == mtime_before


def test_extract_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "Plantseg.zip"
    _make_zip(zip_path, content=b"extracted content")

    dest_dir = tmp_path / "extracted"
    extract_zip(zip_path, dest_dir)

    assert (dest_dir / "inner.txt").read_bytes() == b"extracted content"
    assert (dest_dir / ".extracted").exists()


def test_extract_zip_skips_if_marker_present(tmp_path: Path) -> None:
    zip_path = tmp_path / "Plantseg.zip"
    _make_zip(zip_path)

    dest_dir = tmp_path / "extracted"
    dest_dir.mkdir()
    (dest_dir / ".extracted").write_text("already done", encoding="utf-8")

    extract_zip(zip_path, dest_dir)

    assert not (dest_dir / "inner.txt").exists()
