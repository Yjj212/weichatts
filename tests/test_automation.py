from pathlib import Path

from PIL import Image, ImageDraw

from wechat_complaint_tool.automation import AutomationCallbacks, BatchAutomationRunner
from wechat_complaint_tool.batch import DetectionItem
from wechat_complaint_tool.capture import SegmentCaptureResult
from wechat_complaint_tool.config import AppConfig, Rect


class FakeCaptureService:
    def __init__(self, list_frames: list[Image.Image] | None = None) -> None:
        self.events: list[tuple[str, object]] = []
        self.list_frames = list(list_frames or [])
        self.capture_calls = 0

    def capture_rect_image(self, rect: Rect) -> Image.Image:
        self.events.append(("capture_list", rect))
        if self.list_frames:
            return self.list_frames.pop(0)

        self.capture_calls += 1
        color_seed = (self.capture_calls * 40) % 255
        return Image.new("RGB", (rect.width, rect.height), (255, color_seed, 255 - color_seed))

    def click_point(self, point: tuple[int, int]) -> None:
        self.events.append(("click", point))

    def capture_current_complaint_segments(self, config: AppConfig, destination_dir: Path) -> SegmentCaptureResult:
        self.events.append(("capture_segments", destination_dir))
        destination_dir.mkdir(parents=True, exist_ok=True)
        image_path = destination_dir / "001.png"
        Image.new("RGB", (80, 80), (255, 255, 255)).save(image_path)
        return SegmentCaptureResult(output_dir=destination_dir, image_paths=[image_path], segment_count=1)

    def scroll_list_region(self, rect: Rect, clicks: int = 8) -> None:
        self.events.append(("scroll_list", clicks))


class FakeOCRService:
    def __init__(self) -> None:
        self.calls = 0

    def detect_list_items(self, image: Image.Image, region: Rect) -> list[DetectionItem]:
        self.calls += 1
        if self.calls == 1:
            return [DetectionItem("Alice", "29.80", "preview", (120, 80), "alice")]
        return []


class RepeatingPageOCRService:
    def __init__(self) -> None:
        self.calls = 0

    def detect_list_items(self, image: Image.Image, region: Rect) -> list[DetectionItem]:
        self.calls += 1
        page = [
            DetectionItem("Alice", "29.80", "preview", (120, 80), "alice|29.80|preview"),
            DetectionItem("Alice", "39.80", "preview", (120, 160), "alice|39.80|preview"),
        ]
        if self.calls <= 2:
            return page
        return []


class OverlappingTailOCRService:
    def __init__(self) -> None:
        self.calls = 0

    def detect_list_items(self, image: Image.Image, region: Rect) -> list[DetectionItem]:
        self.calls += 1
        if self.calls == 1:
            return [
                DetectionItem("A", "10.00", "p1", (120, 80), "a|10.00|p1"),
                DetectionItem("B", "20.00", "p2", (120, 160), "b|20.00|p2"),
            ]
        if self.calls == 2:
            return [
                DetectionItem("B", "20.00", "p2", (120, 80), "b|20.00|p2"),
                DetectionItem("C", "30.00", "p3", (120, 160), "c|30.00|p3"),
            ]
        return [
            DetectionItem("B", "20.00", "p2", (120, 80), "b|20.00|p2"),
            DetectionItem("C", "30.00", "p3", (120, 160), "c|30.00|p3"),
        ]


class OCRJitterOnOverlapService:
    def __init__(self) -> None:
        self.calls = 0

    def detect_list_items(self, image: Image.Image, region: Rect) -> list[DetectionItem]:
        self.calls += 1
        if self.calls == 1:
            return [
                DetectionItem("A", "10.00", "p1", (120, 60), "a|10.00|p1", row_top=40, row_bottom=80),
                DetectionItem("B", None, "tail-old", (120, 240), "b|tail-old", row_top=220, row_bottom=260),
            ]
        if self.calls == 2:
            return [
                DetectionItem("2026/2/15", "29.90", "tail-jitter", (120, 60), "date|29.90|tail-jitter", row_top=40, row_bottom=80),
                DetectionItem("B_VARIANT", "99.94", "tail-old-variant", (120, 100), "b2|99.94|tail-old-variant", row_top=82, row_bottom=122),
                DetectionItem("C", "30.00", "fresh", (120, 220), "c|30.00|fresh", row_top=200, row_bottom=240),
            ]
        return []


def _build_overlapping_list_frames() -> list[Image.Image]:
    width = 200
    height = 300
    canvas = Image.new("RGB", (width, 480), (250, 250, 250))
    draw = ImageDraw.Draw(canvas)

    for top, label, fill in [
        (40, "A", (224, 242, 255)),
        (220, "B", (229, 255, 229)),
        (400, "C", (255, 239, 224)),
    ]:
        draw.rounded_rectangle((18, top, 182, top + 42), radius=10, fill=fill, outline=(120, 120, 120))
        draw.text((30, top + 12), label, fill=(0, 0, 0))

    page1 = canvas.crop((0, 0, width, height))
    page2 = canvas.crop((0, 180, width, 180 + height))
    empty3 = Image.new("RGB", (width, height), (243, 243, 243))
    empty4 = Image.new("RGB", (width, height), (242, 242, 242))
    return [page1, page2, empty3, empty4]


def test_batch_runner_waits_1500ms_after_click_before_capture(monkeypatch, tmp_path: Path) -> None:
    waits: list[int] = []

    def fake_wait(delay_ms: int) -> None:
        waits.append(delay_ms)

    monkeypatch.setattr("wechat_complaint_tool.automation.wait_for_ui_settle", fake_wait)

    config = AppConfig(
        output_dir=str(tmp_path),
        list_region=Rect(0, 0, 200, 300),
        content_region=Rect(0, 0, 400, 600),
        scroll_settle_ms=900,
    )
    capture_service = FakeCaptureService()
    ocr_service = FakeOCRService()
    runner = BatchAutomationRunner(config, capture_service, ocr_service, tmp_path)

    callbacks = AutomationCallbacks(on_status=lambda message: None, on_progress=lambda *args: None)

    runner.run(callbacks)

    click_index = capture_service.events.index(("click", (120, 80)))
    segment_event = next(index for index, event in enumerate(capture_service.events) if event[0] == "capture_segments")

    assert click_index < segment_event
    assert 1500 in waits


def test_batch_runner_stops_after_repeated_tail_page_without_recapturing(monkeypatch, tmp_path: Path) -> None:
    waits: list[int] = []

    def fake_wait(delay_ms: int) -> None:
        waits.append(delay_ms)

    monkeypatch.setattr("wechat_complaint_tool.automation.wait_for_ui_settle", fake_wait)

    config = AppConfig(
        output_dir=str(tmp_path),
        list_region=Rect(0, 0, 200, 300),
        content_region=Rect(0, 0, 400, 600),
        scroll_settle_ms=900,
    )
    capture_service = FakeCaptureService()
    ocr_service = RepeatingPageOCRService()
    runner = BatchAutomationRunner(config, capture_service, ocr_service, tmp_path)

    callbacks = AutomationCallbacks(on_status=lambda message: None, on_progress=lambda *args: None)

    runner.run(callbacks)

    captured_dirs = [event for event in capture_service.events if event[0] == "capture_segments"]

    assert len(captured_dirs) == 2
    assert ocr_service.calls == 2


def test_batch_runner_skips_seen_overlap_items_on_tail_pages(monkeypatch, tmp_path: Path) -> None:
    waits: list[int] = []

    def fake_wait(delay_ms: int) -> None:
        waits.append(delay_ms)

    monkeypatch.setattr("wechat_complaint_tool.automation.wait_for_ui_settle", fake_wait)

    config = AppConfig(
        output_dir=str(tmp_path),
        list_region=Rect(0, 0, 200, 300),
        content_region=Rect(0, 0, 400, 600),
        scroll_settle_ms=900,
    )
    capture_service = FakeCaptureService()
    ocr_service = OverlappingTailOCRService()
    runner = BatchAutomationRunner(config, capture_service, ocr_service, tmp_path)

    callbacks = AutomationCallbacks(on_status=lambda message: None, on_progress=lambda *args: None)

    runner.run(callbacks)

    captured_dirs = [event[1].name for event in capture_service.events if event[0] == "capture_segments"]

    assert captured_dirs == ["0001_A_10.00", "0002_B_20.00", "0003_C_30.00"]


def test_batch_runner_skips_visual_overlap_items_even_when_ocr_text_jitters(monkeypatch, tmp_path: Path) -> None:
    waits: list[int] = []

    def fake_wait(delay_ms: int) -> None:
        waits.append(delay_ms)

    monkeypatch.setattr("wechat_complaint_tool.automation.wait_for_ui_settle", fake_wait)

    config = AppConfig(
        output_dir=str(tmp_path),
        list_region=Rect(0, 0, 200, 300),
        content_region=Rect(0, 0, 400, 600),
        scroll_settle_ms=900,
    )
    capture_service = FakeCaptureService(list_frames=_build_overlapping_list_frames())
    ocr_service = OCRJitterOnOverlapService()
    runner = BatchAutomationRunner(config, capture_service, ocr_service, tmp_path)

    callbacks = AutomationCallbacks(on_status=lambda message: None, on_progress=lambda *args: None)

    runner.run(callbacks)

    captured_dirs = [event[1].name for event in capture_service.events if event[0] == "capture_segments"]

    assert captured_dirs == ["0001_A_10.00", "0002_B", "0003_C_30.00"]
