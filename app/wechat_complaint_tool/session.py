from __future__ import annotations

from pathlib import Path
import re
from dataclasses import dataclass


_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACE_RUN = re.compile(r"\s+")


@dataclass(slots=True)
class CaptureTarget:
    index: int
    display_name: str
    amount_label: str | None = None

    @property
    def folder_name(self) -> str:
        parts = [f"{self.index:04d}", sanitize_name(self.display_name)]
        if self.amount_label:
            parts.append(sanitize_name(self.amount_label))
        return "_".join(filter(None, parts))


def sanitize_name(value: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", value.strip())
    cleaned = _SPACE_RUN.sub(" ", cleaned)
    return cleaned[:80] or "unknown"


def build_capture_dir(base_output_dir: Path, target: CaptureTarget) -> Path:
    return base_output_dir / target.folder_name
