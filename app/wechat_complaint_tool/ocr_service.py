from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from .batch import DetectionItem
from .config import Rect
from .detection import DetectionCandidate, cluster_detection_rows


@dataclass(slots=True)
class OCRService:
    engine: RapidOCR | None = None

    def __post_init__(self) -> None:
        if self.engine is None:
            self.engine = RapidOCR()

    def detect_list_items(self, image: Image.Image, region: Rect) -> list[DetectionItem]:
        result, _ = self.engine(np.asarray(image))
        if not result:
            return []

        candidates: list[DetectionCandidate] = []
        for box, text, _score in result:
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            candidates.append(DetectionCandidate(text=text, box=(min(xs), min(ys), max(xs), max(ys))))

        rows = cluster_detection_rows(candidates)
        items: list[DetectionItem] = []
        for row in rows:
            click_point = (region.left + row.center[0], region.top + row.center[1])
            items.append(
                DetectionItem(
                    display_name=row.primary_text,
                    amount_text=row.amount_text,
                    preview_text=row.preview_text,
                    click_point=click_point,
                    fingerprint=row.fingerprint,
                    row_top=row.top,
                    row_bottom=row.bottom,
                )
            )
        return items

    def save_debug_image(self, image: Image.Image, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
