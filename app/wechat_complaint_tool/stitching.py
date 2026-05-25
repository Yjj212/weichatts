from __future__ import annotations

import numpy as np
from PIL import Image


class LongImageComposer:
    def __init__(self, overlap_threshold: float = 0.98, minimum_overlap: int = 20) -> None:
        self.overlap_threshold = overlap_threshold
        self.minimum_overlap = minimum_overlap
        self.horizontal_margin_ratio = 0.12
        self.pixel_tolerance = 2
        self.band_count = 3
        self.informative_row_gradient_threshold = 1.4
        self.minimum_informative_rows = 6
        self.overlap_bonus_weight = 0.12
        self.consistency_weight = 0.04

    def compose(self, frames: list[Image.Image]) -> Image.Image:
        if not frames:
            raise ValueError("At least one frame is required.")

        stitched = frames[0]
        for frame in frames[1:]:
            stitched = self._append_frame(stitched, frame)
        return stitched

    def _append_frame(self, base: Image.Image, incoming: Image.Image) -> Image.Image:
        overlap = self._find_overlap(base, incoming)
        if overlap >= incoming.height:
            return base

        new_height = base.height + incoming.height - overlap
        canvas = Image.new("RGB", (base.width, new_height))
        canvas.paste(base, (0, 0))
        canvas.paste(incoming.crop((0, overlap, incoming.width, incoming.height)), (0, base.height))
        return canvas

    def _find_overlap(self, base: Image.Image, incoming: Image.Image) -> int:
        base_arr = np.asarray(base)
        incoming_arr = np.asarray(incoming)
        max_overlap = min(base.height, incoming.height)
        start_x, end_x = self._stable_horizontal_window(base.width)
        best_overlap = 0
        best_score = 0.0

        for overlap in range(max_overlap, self.minimum_overlap - 1, -1):
            base_slice = base_arr[base.height - overlap : base.height, start_x:end_x]
            incoming_slice = incoming_arr[:overlap, start_x:end_x]
            if base_slice.shape != incoming_slice.shape:
                continue

            similarity, consistency = self._score_overlap(base_slice, incoming_slice)
            if similarity < self.overlap_threshold:
                continue

            score = similarity + consistency * self.consistency_weight + (overlap / max_overlap) * self.overlap_bonus_weight
            if score > best_score or (abs(score - best_score) < 1e-6 and overlap > best_overlap):
                best_score = score
                best_overlap = overlap
        return best_overlap

    def _stable_horizontal_window(self, width: int) -> tuple[int, int]:
        margin = max(4, int(width * self.horizontal_margin_ratio))
        start_x = margin
        end_x = max(start_x + 1, width - margin)
        return start_x, end_x

    def _score_overlap(self, base_slice: np.ndarray, incoming_slice: np.ndarray) -> tuple[float, float]:
        match_map = self._build_match_map(base_slice, incoming_slice)
        informative_rows = self._informative_rows(base_slice, incoming_slice)
        minimum_rows = min(match_map.shape[0], max(self.minimum_informative_rows, match_map.shape[0] // 8))
        if int(np.count_nonzero(informative_rows)) >= minimum_rows:
            match_map = match_map[informative_rows]

        band_scores = self._band_scores(match_map)
        similarity = float(np.median(band_scores))
        consistency = float(np.mean(band_scores >= self.overlap_threshold))
        return similarity, consistency

    def _build_match_map(self, base_slice: np.ndarray, incoming_slice: np.ndarray) -> np.ndarray:
        diff = np.abs(base_slice.astype(np.int16) - incoming_slice.astype(np.int16))
        return np.max(diff, axis=2) <= self.pixel_tolerance

    def _informative_rows(self, base_slice: np.ndarray, incoming_slice: np.ndarray) -> np.ndarray:
        if base_slice.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        base_energy = self._row_gradient_energy(base_slice)
        incoming_energy = self._row_gradient_energy(incoming_slice)
        return np.maximum(base_energy, incoming_energy) >= self.informative_row_gradient_threshold

    def _row_gradient_energy(self, image_slice: np.ndarray) -> np.ndarray:
        if image_slice.shape[1] <= 1:
            return np.zeros(image_slice.shape[0], dtype=float)
        horizontal_diff = np.diff(image_slice.astype(np.int16), axis=1)
        return np.mean(np.abs(horizontal_diff), axis=(1, 2))

    def _band_scores(self, match_map: np.ndarray) -> np.ndarray:
        if match_map.size == 0:
            return np.array([0.0], dtype=float)
        bands = [band for band in np.array_split(match_map, self.band_count, axis=1) if band.size]
        return np.array([float(np.mean(band)) for band in bands], dtype=float)
