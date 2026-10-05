from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.log import get_logger

log = get_logger(__name__)

# Embedded JPEGs in a NEF, best quality first. JpgFromRaw is full resolution on
# Z-series bodies; PreviewImage is ~1-2MP; OtherImage appears on some models.
PREVIEW_TAGS = ("JpgFromRaw", "PreviewImage", "OtherImage")


class ExifToolError(RuntimeError):
    pass


@dataclass(slots=True)
class ExifDump:
    """ExifTool output keyed by `Group:Tag`.

    `printed` holds human-readable values ("1/500", "Matrix"); `numeric` holds
    machine values (0.002, 5) for tags where they differ.
    """

    printed: dict[str, Any] = field(default_factory=dict)
    numeric: dict[str, Any] = field(default_factory=dict)

    def get(self, *keys: str, numeric: bool = False) -> Any:
        for key in keys:
            if numeric and key in self.numeric:
                return self.numeric[key]
            if key in self.printed:
                return self.printed[key]
        return None

    def to_json(self) -> dict[str, Any]:
        return {"printed": self.printed, "numeric": self.numeric}

    @classmethod
    def from_long_json(cls, item: dict[str, Any]) -> ExifDump:
        """Parse one element of `exiftool -j -G -l` output."""
        dump = cls()
        for key, entry in item.items():
            if key == "SourceFile":
                continue
            if isinstance(entry, dict) and "val" in entry:
                dump.printed[key] = entry["val"]
                if "num" in entry and entry["num"] != entry["val"]:
                    dump.numeric[key] = entry["num"]
            else:
                dump.printed[key] = entry
        return dump


def _run(args: list[str], timeout: float = 60.0) -> subprocess.CompletedProcess[bytes]:
    settings = get_settings()
    try:
        return subprocess.run(
            [settings.exiftool_path, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ExifToolError("exiftool binary not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExifToolError(f"exiftool timed out after {timeout}s") from exc


def read_metadata(path: Path) -> ExifDump:
    """Read all metadata (read-only: exiftool never writes without -o/-overwrite)."""
    proc = _run(["-j", "-G", "-l", "-a", "-u", "-api", "LargeFileSupport=1", "--", str(path)])
    if not proc.stdout.strip():
        err = proc.stderr.decode(errors="replace").strip()
        raise ExifToolError(err or f"exiftool returned no data (exit {proc.returncode})")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExifToolError(f"invalid exiftool JSON: {exc}") from exc
    if not data:
        raise ExifToolError("exiftool returned an empty result")
    item = data[0]
    if "ExifTool:Error" in item:
        raise ExifToolError(str(item["ExifTool:Error"].get("val", item["ExifTool:Error"])))
    return ExifDump.from_long_json(item)


def extract_embedded_preview(path: Path) -> bytes | None:
    """Return the largest embedded JPEG from a RAW file, or None."""
    best: bytes | None = None
    for tag in PREVIEW_TAGS:
        proc = _run(["-b", f"-{tag}", "--", str(path)], timeout=60)
        data = proc.stdout
        if data and data[:2] == b"\xff\xd8" and (best is None or len(data) > len(best)):
            best = data
            if tag == "JpgFromRaw" and len(data) > 1_000_000:
                break
    return best


def exiftool_version() -> str | None:
    try:
        proc = _run(["-ver"], timeout=10)
        return proc.stdout.decode().strip() or None
    except ExifToolError:
        return None
