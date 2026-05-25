from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import threading

from .batch import BatchCoordinator, BatchPage, DetectionItem, RunManifest
from .capture import (
    DEFAULT_MINIMUM_OVERLAP,
    ScreenCaptureService,
    detect_list_page_overlap,
    validate_capture_prerequisites,
    wait_for_ui_settle,
)
from .config import AppConfig
from .ocr_service import OCRService
from .session import CaptureTarget, build_capture_dir

POST_CLICK_SETTLE_MS = 1500


@dataclass(slots=True)
class AutomationCallbacks:
    on_status: callable
    on_progress: callable


class BatchAutomationRunner:
    def __init__(self, config: AppConfig, capture_service: ScreenCaptureService, ocr_service: OCRService, base_dir: Path) -> None:
        self.config = config
        self.capture_service = capture_service
        self.ocr_service = ocr_service
        self.base_dir = base_dir
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_requested = False

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_requested = True
        self._pause_event.set()

    def run(self, callbacks: AutomationCallbacks) -> Path:
        issues = validate_capture_prerequisites(self.config)
        if issues:
            raise ValueError("\n".join(issues))

        run_dir = self._prepare_run_dir()
        manifest = RunManifest(run_dir=run_dir, entries=[], failures=[])
        coordinator = BatchCoordinator(manifest=manifest)
        processed_index = 0
        previous_list_image = None

        while True:
            self._pause_event.wait()
            if self._stop_requested:
                break

            list_image = self.capture_service.capture_rect_image(self.config.list_region)
            overlap_height = (
                detect_list_page_overlap(previous_list_image, list_image, minimum_overlap=DEFAULT_MINIMUM_OVERLAP)
                if previous_list_image is not None
                else 0
            )
            page_items = self._filter_items_in_overlap(
                self.ocr_service.detect_list_items(list_image, self.config.list_region),
                overlap_height,
            )
            page = BatchPage(page_items)
            seen_before_page = set(coordinator.seen_fingerprints)
            should_stop = coordinator.register_page(page.items)
            new_items = page.new_items(seen_before_page)
            previous_list_image = list_image

            if should_stop:
                callbacks.on_status("连续两页没有识别到新投诉，批量结束。")
                break

            if not new_items:
                callbacks.on_status("当前页没有新投诉，滚动左侧列表。")
                self._scroll_list_page()
                continue

            for item in new_items:
                self._pause_event.wait()
                if self._stop_requested:
                    break

                processed_index += 1
                callbacks.on_status(f"正在处理第 {processed_index} 条：{item.display_name} {item.amount_text or ''}".strip())
                try:
                    self.capture_service.click_point(item.click_point)
                    wait_for_ui_settle(POST_CLICK_SETTLE_MS)

                    target = CaptureTarget(
                        index=processed_index,
                        display_name=item.display_name or "unknown",
                        amount_label=item.amount_text,
                    )
                    destination_dir = build_capture_dir(run_dir, target)
                    result = self.capture_service.capture_current_complaint_segments(self.config, destination_dir)
                    coordinator.record_success(
                        item,
                        {
                            "output_dir": str(result.output_dir),
                            "segment_count": result.segment_count,
                        },
                    )
                    callbacks.on_progress(
                        len(manifest.entries),
                        len(manifest.failures),
                        item.display_name,
                        item.amount_text or "",
                    )
                    callbacks.on_status(
                        f"第 {processed_index} 条已保存 {result.segment_count} 张：{result.output_dir}"
                    )
                except Exception as exc:  # noqa: BLE001
                    should_pause = coordinator.record_failure(f"{processed_index:04d}", str(exc))
                    callbacks.on_status(f"第 {processed_index} 条失败：{exc}")
                    if should_pause:
                        self.pause()
                        callbacks.on_status("连续失败过多，已自动暂停，请检查微信界面。")
                        break

            if self._stop_requested:
                break
            self._scroll_list_page()

        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(
            json.dumps({"entries": manifest.entries, "failures": manifest.failures}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def _prepare_run_dir(self) -> Path:
        root = Path(self.config.output_dir)
        if not root.is_absolute():
            root = self.base_dir / root
        run_dir = root / datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _scroll_list_page(self) -> None:
        if self.config.list_region is None:
            return
        rect = self.config.list_region
        self.capture_service.scroll_list_region(rect, clicks=int(10 * self.config.list_page_scroll_ratio))
        wait_for_ui_settle(self.config.scroll_settle_ms)

    @staticmethod
    def _filter_items_in_overlap(
        items: list[DetectionItem],
        overlap_height: int,
        overlap_guard_px: int = 8,
    ) -> list[DetectionItem]:
        if overlap_height <= 0:
            return items

        boundary = max(overlap_height - overlap_guard_px, 0)
        filtered = [item for item in items if item.row_top >= boundary]
        return filtered or items
