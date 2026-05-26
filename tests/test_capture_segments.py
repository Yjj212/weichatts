from pathlib import Path

from PIL import Image

from wechat_complaint_tool.capture import ScreenCaptureService, crop_order_info_frame
from wechat_complaint_tool.config import AppConfig, Rect


class FakeCaptureService(ScreenCaptureService):
    def __init__(self, frames: list[Image.Image]) -> None:
        super().__init__()
        self.frames = list(frames)
        self.scroll_calls = 0

    def capture_rect_image(self, rect: Rect) -> Image.Image:
        return self.frames.pop(0)

    def scroll_chat_region(self, rect: Rect, clicks: int = 8) -> None:  # type: ignore[override]
        self.scroll_calls += 1

    def save_image(self, image: Image.Image, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        return destination


def test_capture_current_complaint_segments_creates_ordered_pngs(tmp_path: Path) -> None:
    config = AppConfig(content_region=Rect(0, 0, 80, 120), chat_scroll_clicks=2, scroll_settle_ms=0)

    first = Image.new("RGB", (80, 120), (255, 255, 255))
    second = Image.new("RGB", (80, 120), (255, 255, 255))
    third = Image.new("RGB", (80, 120), (255, 255, 255))
    for y in range(60):
        for x in range(80):
            color = (y * 3, 0, 0)
            first.putpixel((x, y), color)
            second.putpixel((x, y + 60), color)
    for y in range(20):
        for x in range(80):
            color = (100 + y * 3, 30, 0)
            second.putpixel((x, y), color)
            third.putpixel((x, y + 100), color)
    fourth = third.copy()

    service = FakeCaptureService([first, second, third, fourth])

    result = service.capture_current_complaint_segments(config, tmp_path, max_scrolls=3)

    assert [path.name for path in result.image_paths] == ["001.png", "002.png", "003.png"]
    assert result.segment_count == 3
    assert (tmp_path / "order_info.png").exists()
    assert service.scroll_calls == 3


def test_capture_current_complaint_segments_saves_top_order_info_after_segment_limit(tmp_path: Path) -> None:
    config = AppConfig(content_region=Rect(0, 0, 40, 60), chat_scroll_clicks=2, scroll_settle_ms=0)
    bottom = Image.new("RGB", (40, 60), (255, 0, 0))
    middle = Image.new("RGB", (40, 60), (0, 255, 0))
    top = Image.new("RGB", (40, 60), (0, 0, 255))
    top_repeat = top.copy()
    service = FakeCaptureService([bottom, middle, top, top_repeat])

    result = service.capture_current_complaint_segments(config, tmp_path, max_scrolls=1)

    assert [path.name for path in result.image_paths] == ["001.png"]
    assert result.segment_count == 1
    order_info = Image.open(tmp_path / "order_info.png")
    try:
        assert order_info.getpixel((0, 0)) == (0, 0, 255)
    finally:
        order_info.close()
    assert service.scroll_calls == 3


def test_capture_current_complaint_segments_stops_after_repeated_frame(tmp_path: Path) -> None:
    config = AppConfig(content_region=Rect(0, 0, 60, 90), chat_scroll_clicks=2, scroll_settle_ms=0)
    first = Image.new("RGB", (60, 90), (255, 255, 255))
    second = Image.new("RGB", (60, 90), (255, 255, 255))
    third = second.copy()

    service = FakeCaptureService([first, second, third])

    result = service.capture_current_complaint_segments(config, tmp_path, max_scrolls=2)

    assert result.segment_count == 1
    assert [path.name for path in result.image_paths] == ["001.png"]
    assert (tmp_path / "order_info.png").exists()


def test_crop_order_info_frame_keeps_top_portion_only() -> None:
    source = Image.new("RGB", (120, 200), (255, 255, 255))
    for y in range(80):
        for x in range(120):
            source.putpixel((x, y), (0, 0, 255))
    for y in range(80, 200):
        for x in range(120):
            source.putpixel((x, y), (255, 0, 0))

    cropped = crop_order_info_frame(source)

    assert cropped.size == (120, 110)
    assert cropped.getpixel((10, 10)) == (0, 0, 255)
    assert cropped.getpixel((10, 100)) == (255, 0, 0)
