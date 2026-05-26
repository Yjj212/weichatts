from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import cv2
import mss
import numpy as np
from PIL import Image
import pyautogui

from .config import AppConfig, Rect


DEFAULT_MINIMUM_OVERLAP = 24
DEFAULT_MINIMUM_NEW_CONTENT_HEIGHT = 24
DEFAULT_PIXEL_TOLERANCE = 2
DEFAULT_HORIZONTAL_MARGIN_RATIO = 0.12
DEFAULT_LIST_OVERLAP_THRESHOLD = 0.985
DEFAULT_ORDER_INFO_MAX_SCROLLS = 24
DEFAULT_ORDER_INFO_HEIGHT_RATIO = 0.55
ORDER_INFO_FILE_NAME = "order_info.png"


@dataclass(slots=True)
class SegmentCaptureResult:
    output_dir: Path
    image_paths: list[Path]
    segment_count: int
    order_info_path: Path | None = None


@dataclass(slots=True)
class PreviewResult:
    output_dir: Path
    image_paths: list[Path]
    segment_count: int

    @property
    def image_path(self) -> Path:
        return self.output_dir

    @property
    def frame_count(self) -> int:
        return self.segment_count


class ScreenCaptureService:
    def capture_rect_image(self, rect: Rect) -> Image.Image:
        with mss.mss() as sct:
            shot = sct.grab({"left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height})
            return Image.frombytes("RGB", shot.size, shot.rgb)

    def save_image(self, image: Image.Image, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        return destination

    def capture_preview_long_image(self, config: AppConfig, destination: Path, max_scrolls: int = 18) -> PreviewResult:
        output_dir = destination if destination.suffix == "" else destination.with_suffix("")
        result = self.capture_current_complaint_segments(config, output_dir, max_scrolls=max_scrolls)
        return PreviewResult(output_dir=result.output_dir, image_paths=result.image_paths, segment_count=result.segment_count)

    def capture_current_complaint_segments(
        self,
        config: AppConfig,
        destination_dir: Path,
        max_scrolls: int = 18,
    ) -> SegmentCaptureResult:
        if config.content_region is None:
            raise ValueError("请先设置右侧完整内容区域")

        rect = config.content_region
        destination_dir.mkdir(parents=True, exist_ok=True)

        first_frame = self.capture_rect_image(rect)
        image_paths = [self.save_image(first_frame, destination_dir / build_segment_file_name(1))]

        previous_full_frame = first_frame
        latest_visible_frame = first_frame
        stagnation_count = 0

        for _ in range(max(max_scrolls - 1, 0)):
            self.scroll_chat_region(rect, clicks=config.chat_scroll_clicks)
            wait_for_ui_settle(config.scroll_settle_ms)

            current_full_frame = self.capture_rect_image(rect)
            if self._is_same_frame(np.asarray(previous_full_frame), np.asarray(current_full_frame)):
                break

            latest_visible_frame = current_full_frame
            cropped_frame, _ = crop_bottom_overlap(
                previous=previous_full_frame,
                current=current_full_frame,
                minimum_overlap=DEFAULT_MINIMUM_OVERLAP,
                threshold=config.capture_overlap_threshold,
            )

            if not has_meaningful_new_content(cropped_frame, minimum_height=DEFAULT_MINIMUM_NEW_CONTENT_HEIGHT):
                stagnation_count += 1
                previous_full_frame = current_full_frame
                if stagnation_count >= 2:
                    break
                continue

            stagnation_count = 0
            image_paths.append(
                self.save_image(cropped_frame, destination_dir / build_segment_file_name(len(image_paths) + 1))
            )
            previous_full_frame = current_full_frame

        order_info_frame = self.capture_order_info_frame(
            rect=rect,
            initial_frame=latest_visible_frame,
            scroll_clicks=config.chat_scroll_clicks,
            settle_ms=config.scroll_settle_ms,
        )
        order_info_path = self.save_image(crop_order_info_frame(order_info_frame), destination_dir / ORDER_INFO_FILE_NAME)
        return SegmentCaptureResult(
            output_dir=destination_dir,
            image_paths=image_paths,
            segment_count=len(image_paths),
            order_info_path=order_info_path,
        )

    @staticmethod
    def scroll_chat_region(rect: Rect, clicks: int = 8) -> None:
        center_x = rect.left + rect.width // 2
        center_y = rect.top + rect.height // 2
        pyautogui.moveTo(center_x, center_y)
        pyautogui.scroll(chat_scroll_wheel_amount(clicks))

    @staticmethod
    def scroll_list_region(rect: Rect, clicks: int = 8) -> None:
        center_x = rect.left + rect.width // 2
        center_y = rect.top + rect.height // 2
        pyautogui.moveTo(center_x, center_y)
        pyautogui.scroll(list_scroll_wheel_amount(clicks))

    @staticmethod
    def click_point(point: tuple[int, int]) -> None:
        pyautogui.click(point[0], point[1])

    def capture_order_info_frame(
        self,
        rect: Rect,
        initial_frame: Image.Image,
        scroll_clicks: int,
        settle_ms: int,
        max_scrolls: int = DEFAULT_ORDER_INFO_MAX_SCROLLS,
    ) -> Image.Image:
        topmost_frame = initial_frame
        for _ in range(max_scrolls):
            self.scroll_chat_region(rect, clicks=scroll_clicks)
            wait_for_ui_settle(settle_ms)
            current_frame = self.capture_rect_image(rect)
            if self._is_same_frame(np.asarray(topmost_frame), np.asarray(current_frame)):
                break
            topmost_frame = current_frame
        return topmost_frame

    @staticmethod
    def _is_same_frame(previous: np.ndarray, current: np.ndarray) -> bool:
        if previous.shape != current.shape:
            return False
        diff = cv2.absdiff(previous, current)
        return float(np.mean(diff)) < 1.2


def validate_capture_prerequisites(config: AppConfig) -> list[str]:
    issues: list[str] = []
    if config.list_region is None:
        issues.append("未设置左侧投诉列表区域")
    if config.content_region is None:
        issues.append("未设置右侧完整内容区域")
    return issues


def wait_for_ui_settle(delay_ms: int) -> None:
    time.sleep(max(delay_ms, 0) / 1000)


def chat_scroll_wheel_amount(clicks: int) -> int:
    return -abs(clicks) * 120


def list_scroll_wheel_amount(clicks: int) -> int:
    return -abs(clicks) * 120


def normalize_bottom_origin_sequence(items: list) -> list:
    return list(items)


def build_segment_file_name(index: int) -> str:
    return f"{index:03d}.png"


def has_meaningful_new_content(image: Image.Image, minimum_height: int = DEFAULT_MINIMUM_NEW_CONTENT_HEIGHT) -> bool:
    return image.height >= minimum_height


def crop_order_info_frame(image: Image.Image, height_ratio: float = DEFAULT_ORDER_INFO_HEIGHT_RATIO) -> Image.Image:
    if image.height <= 0:
        return image
    crop_height = max(1, min(image.height, int(round(image.height * height_ratio))))
    return image.crop((0, 0, image.width, crop_height))


def detect_list_page_overlap(
    previous: Image.Image,
    current: Image.Image,
    minimum_overlap: int = DEFAULT_MINIMUM_OVERLAP,
    threshold: float = DEFAULT_LIST_OVERLAP_THRESHOLD,
) -> int:
    previous_arr = np.asarray(previous)
    current_arr = np.asarray(current)
    if previous_arr.shape != current_arr.shape:
        return 0

    max_overlap = min(previous.height, current.height)
    start_x, end_x = _stable_horizontal_window(previous.width)
    best_overlap = 0
    best_score = 0.0

    for overlap in range(max_overlap, minimum_overlap - 1, -1):
        previous_slice = previous_arr[previous.height - overlap : previous.height, start_x:end_x]
        current_slice = current_arr[:overlap, start_x:end_x]
        if previous_slice.shape != current_slice.shape:
            continue

        similarity = np.mean(
            np.abs(previous_slice.astype(np.int16) - current_slice.astype(np.int16)) <= DEFAULT_PIXEL_TOLERANCE
        )
        if similarity < threshold:
            continue

        score = float(similarity) + (overlap / max_overlap) * 0.1
        if score > best_score or (abs(score - best_score) < 1e-6 and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    return best_overlap


def crop_bottom_overlap(
    previous: Image.Image,
    current: Image.Image,
    minimum_overlap: int = DEFAULT_MINIMUM_OVERLAP,
    threshold: float = 0.98,
) -> tuple[Image.Image, int]:
    previous_arr = np.asarray(previous)
    current_arr = np.asarray(current)
    max_overlap = min(previous.height, current.height)
    start_x, end_x = _stable_horizontal_window(previous.width)
    best_overlap = 0
    best_score = 0.0

    for overlap in range(max_overlap, minimum_overlap - 1, -1):
        previous_slice = previous_arr[:overlap, start_x:end_x]
        current_slice = current_arr[current.height - overlap : current.height, start_x:end_x]
        if previous_slice.shape != current_slice.shape:
            continue

        similarity = np.mean(
            np.abs(previous_slice.astype(np.int16) - current_slice.astype(np.int16)) <= DEFAULT_PIXEL_TOLERANCE
        )
        if similarity < threshold:
            continue

        score = float(similarity) + (overlap / max_overlap) * 0.1
        if score > best_score or (abs(score - best_score) < 1e-6 and overlap > best_overlap):
            best_score = score
            best_overlap = overlap

    if best_overlap <= 0:
        return current, 0

    cropped_height = max(current.height - best_overlap, 0)
    cropped = current.crop((0, 0, current.width, cropped_height))
    return cropped, best_overlap


def _stable_horizontal_window(width: int) -> tuple[int, int]:
    margin = max(4, int(width * DEFAULT_HORIZONTAL_MARGIN_RATIO))
    start_x = margin
    end_x = max(start_x + 1, width - margin)
    return start_x, end_x
