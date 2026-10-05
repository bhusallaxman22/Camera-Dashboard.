from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from app.models.enums import FileType
from app.utils.paths import (
    UnsafePathError,
    base_name,
    classify,
    date_from_directory,
    resolve_under_roots,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("DSC_1234.JPG", FileType.JPEG),
        ("dsc_1234.jpeg", FileType.JPEG),
        ("DSC_1234.NEF", FileType.RAW),
        ("DSC_1234.nef", FileType.RAW),
        ("DSC_1234.HIF", FileType.IMAGE),
        ("DSC_1234.MOV", FileType.VIDEO),
        ("DSC_1234.MP4", FileType.VIDEO),
        ("DSC_1234.NEF.part", None),
        ("DSC_1234.JPG.filepart", None),
        (".DSC_1234.JPG", None),
        ("._DSC_1234.JPG", None),
        ("notes.txt", None),
        ("Thumbs.db", None),
    ],
)
def test_classify(name: str, expected: FileType | None) -> None:
    assert classify(name) == expected


def test_base_name_and_directory_date() -> None:
    assert base_name("/photos/raw/2026/09/30/DSC_1234.NEF") == "DSC_1234"
    assert base_name("/photos/immich-jpeg/2026/10/01/DSC_0111_072752.JPG") == "DSC_0111"
    assert base_name("/photos/raw/_DSC0111_072752.NEF") == "_DSC0111"
    assert base_name("/photos/raw/Z63_0111_072752.NEF") == "Z63_0111"
    assert base_name("/photos/raw/holiday_2026_072752.JPG") == "holiday_2026_072752"
    assert base_name("/photos/raw/DSC_0111_72752.JPG") == "DSC_0111_72752"
    assert base_name("/photos/immich-jpeg/DSC_0117-1.JPG") == "DSC_0117"
    assert base_name("/photos/immich-jpeg/DSC_0119-1_162816.JPG") == "DSC_0119"
    assert base_name("/photos/immich-jpeg/test-1.jpg") == "test-1"
    assert date_from_directory("/photos/raw/2026/09/30/DSC_1234.NEF") == date(2026, 9, 30)
    assert date_from_directory("/photos/raw/unsorted/DSC_1234.NEF") is None
    assert date_from_directory("/photos/raw/2026/13/40/DSC_1234.NEF") is None


def test_resolve_under_roots_accepts_inside(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    (root / "raw").mkdir(parents=True)
    f = root / "raw" / "a.NEF"
    f.write_bytes(b"x")
    assert resolve_under_roots(f, [root]) == f.resolve()


@pytest.mark.parametrize("evil", ["../../etc/passwd", "raw/../../secret", "/etc/passwd"])
def test_resolve_under_roots_rejects_traversal(tmp_path: Path, evil: str) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    with pytest.raises(UnsafePathError):
        resolve_under_roots(root / evil if not evil.startswith("/") else evil, [root])


def test_resolve_under_roots_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = root / "link.JPG"
    os.symlink(outside, link)
    with pytest.raises(UnsafePathError):
        resolve_under_roots(link, [root])


def test_resolve_under_roots_rejects_prefix_sibling(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    sibling = tmp_path / "photos-evil"
    sibling.mkdir()
    with pytest.raises(UnsafePathError):
        resolve_under_roots(sibling / "x.JPG", [root])


def test_resolve_rejects_nul() -> None:
    with pytest.raises(UnsafePathError):
        resolve_under_roots("/photos/a\x00.JPG", [Path("/photos")])


def test_empty_unsorted_root_disables_it(monkeypatch) -> None:
    from app.config import Settings

    monkeypatch.setenv("UNSORTED_ROOT", "")
    assert "unsorted" not in Settings().media_roots
    monkeypatch.setenv("UNSORTED_ROOT", "/photos/unsorted")
    assert Settings().media_roots["unsorted"] == Path("/photos/unsorted")


@pytest.mark.parametrize(
    ("share", "expected"),
    [
        ("\\\\truenas\\photos\\z6iii", "\\\\truenas\\photos\\z6iii\\raw\\2026\\DSC_1.NEF"),
        ("\\\\truenas\\photos\\z6iii\\", "\\\\truenas\\photos\\z6iii\\raw\\2026\\DSC_1.NEF"),
        ("192.168.0.142\\Z6III_Photos", "\\\\192.168.0.142\\Z6III_Photos\\raw\\2026\\DSC_1.NEF"),
        ("//truenas/photos", "\\\\truenas\\photos\\raw\\2026\\DSC_1.NEF"),
        ("smb://truenas/photos/", "smb://truenas/photos/raw/2026/DSC_1.NEF"),
        ("", None),
    ],
)
def test_smb_path_normalizes_share(share: str, expected: str | None) -> None:
    from app.config import Settings

    s = Settings(photo_root=Path("/photos"), smb_photo_root=share)
    assert s.smb_path("/photos/raw/2026/DSC_1.NEF") == expected
    assert s.smb_path("/etc/passwd") is None
