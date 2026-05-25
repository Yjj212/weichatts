# WeChat Segment Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the right-side long-image stitching flow with per-complaint segmented screenshots while keeping the left-side automatic user switching and paging flow.

**Architecture:** Keep the existing OCR-driven left list detection and batch coordinator, but swap the right-side capture path from "collect frames then stitch one PNG" to "capture one complaint into a folder of ordered PNG segments". Add a lightweight overlap-cropping helper for adjacent screenshots, route preview/batch through the new folder-based API, and downgrade long-image-specific UI wording and manifest fields.

**Tech Stack:** Python 3.14, Pillow, NumPy, pytest, Tkinter, existing screen automation services

---

### Task 1: Add failing tests for segmented screenshot capture outputs

**Files:**
- Modify: `tests/test_capture_order.py`
- Modify: `tests/test_batch.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from wechat_complaint_tool.capture import build_segment_file_name, normalize_bottom_origin_sequence


def test_build_segment_file_name_uses_three_digit_sequence() -> None:
    assert build_segment_file_name(1) == "001.png"
    assert build_segment_file_name(12) == "012.png"


def test_normalize_bottom_origin_sequence_keeps_bottom_first_order() -> None:
    captured = ["bottom", "upper"]

    assert normalize_bottom_origin_sequence(captured) == ["bottom", "upper"]
```

```python
from pathlib import Path

from wechat_complaint_tool.batch import DetectionItem, RunManifest
from wechat_complaint_tool.session import CaptureTarget, build_capture_dir


def test_build_capture_dir_uses_target_folder_name_without_timestamp(tmp_path: Path) -> None:
    target = CaptureTarget(index=3, display_name="Alice", amount_label="39.80")

    path = build_capture_dir(tmp_path, target)

    assert path == tmp_path / "0003_Alice_39.80"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.14 -m pytest -q tests/test_capture_order.py tests/test_batch.py`
Expected: FAIL because the segmented filename helper does not exist yet and `build_capture_dir` still appends a timestamp.

- [ ] **Step 3: Write minimal implementation**

```python
def build_segment_file_name(index: int) -> str:
    return f"{index:03d}.png"


def normalize_bottom_origin_sequence(items: list) -> list:
    return list(items)
```

```python
def build_capture_dir(base_output_dir: Path, target: CaptureTarget, now: datetime | None = None) -> Path:
    return base_output_dir / target.folder_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.14 -m pytest -q tests/test_capture_order.py tests/test_batch.py`
Expected: PASS

### Task 2: Add failing tests for adjacent-frame overlap cropping

**Files:**
- Modify: `tests/test_capture_order.py`
- Modify: `app/wechat_complaint_tool/capture.py`

- [ ] **Step 1: Write the failing tests**

```python
from PIL import Image

from wechat_complaint_tool.capture import crop_bottom_overlap, has_meaningful_new_content


def test_crop_bottom_overlap_removes_repeated_bottom_band() -> None:
    top = Image.new("RGB", (80, 120), (255, 255, 255))
    bottom = Image.new("RGB", (80, 120), (255, 255, 255))
    for y in range(60):
        for x in range(80):
            color = (y * 2, 0, 0)
            top.putpixel((x, y), color)
            bottom.putpixel((x, y + 60), color)

    cropped, overlap = crop_bottom_overlap(previous=top, current=bottom, minimum_overlap=20, threshold=0.98)

    assert overlap == 60
    assert cropped.height == 60


def test_has_meaningful_new_content_rejects_tiny_remainder() -> None:
    image = Image.new("RGB", (120, 18), (255, 255, 255))

    assert has_meaningful_new_content(image, minimum_height=24) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.14 -m pytest -q tests/test_capture_order.py -k overlap`
Expected: FAIL because `crop_bottom_overlap` and `has_meaningful_new_content` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def crop_bottom_overlap(previous: Image.Image, current: Image.Image, minimum_overlap: int, threshold: float) -> tuple[Image.Image, int]:
    # compare previous top against current bottom, crop repeated bottom region from current
```

```python
def has_meaningful_new_content(image: Image.Image, minimum_height: int = 24) -> bool:
    return image.height >= minimum_height
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.14 -m pytest -q tests/test_capture_order.py -k overlap`
Expected: PASS

### Task 3: Add failing tests for current-complaint segmented capture workflow

**Files:**
- Create: `tests/test_capture_segments.py`
- Modify: `app/wechat_complaint_tool/capture.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from PIL import Image

from wechat_complaint_tool.capture import ScreenCaptureService
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


def test_capture_current_complaint_segments_creates_ordered_pngs(tmp_path: Path) -> None:
    config = AppConfig(content_region=Rect(0, 0, 80, 120), chat_scroll_clicks=2, scroll_settle_ms=0)
    first = Image.new("RGB", (80, 120), (255, 255, 255))
    second = Image.new("RGB", (80, 80), (240, 240, 240)).resize((80, 120))
    third = second.copy()
    service = FakeCaptureService([first, second, third])

    result = service.capture_current_complaint_segments(config, tmp_path, max_scrolls=3)

    assert [path.name for path in result.image_paths] == ["001.png", "002.png"]
    assert result.segment_count == 2
    assert service.scroll_calls >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.14 -m pytest -q tests/test_capture_segments.py`
Expected: FAIL because `capture_current_complaint_segments` and its result type do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class SegmentCaptureResult:
    output_dir: Path
    image_paths: list[Path]
    segment_count: int
```

```python
def capture_current_complaint_segments(self, config: AppConfig, destination_dir: Path, max_scrolls: int = 18) -> SegmentCaptureResult:
    # capture first frame, save ordered pngs, stop when repeated/no-new-content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.14 -m pytest -q tests/test_capture_segments.py`
Expected: PASS

### Task 4: Add failing tests for batch manifest folder recording

**Files:**
- Modify: `tests/test_batch.py`
- Modify: `app/wechat_complaint_tool/automation.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from wechat_complaint_tool.batch import DetectionItem, RunManifest
from wechat_complaint_tool.session import CaptureTarget


def test_manifest_records_output_folder_and_segment_count(tmp_path: Path) -> None:
    manifest = RunManifest(run_dir=tmp_path, entries=[], failures=[])
    item = DetectionItem("Alice", "39.80", "preview", (10, 10), "fp-1")

    manifest.entries.append(
        {
            "fingerprint": item.fingerprint,
            "display_name": item.display_name,
            "amount_text": item.amount_text,
            "output_dir": str(tmp_path / "0001_Alice_39.80"),
            "segment_count": 3,
        }
    )

    assert manifest.entries[0]["output_dir"].endswith("0001_Alice_39.80")
    assert manifest.entries[0]["segment_count"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.14 -m pytest -q tests/test_batch.py -k segment_count`
Expected: FAIL after you update existing tests to assert the old image-path behavior is gone.

- [ ] **Step 3: Write minimal implementation**

```python
coordinator.record_success(
    item,
    {
        "output_dir": str(result.output_dir),
        "segment_count": result.segment_count,
    },
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.14 -m pytest -q tests/test_batch.py -k segment_count`
Expected: PASS

### Task 5: Route preview and batch automation to the segmented capture path

**Files:**
- Modify: `app/wechat_complaint_tool/automation.py`
- Modify: `app/wechat_complaint_tool/gui.py`
- Modify: `app/wechat_complaint_tool/session.py`

- [ ] **Step 1: Write the failing tests**

Add a GUI-adjacent unit test that checks preview status text now refers to segmented images and directory output.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.14 -m pytest -q tests/test_session.py tests/test_batch.py`
Expected: FAIL because preview/batch still expect long-image file output and timestamped per-run folders.

- [ ] **Step 3: Write minimal implementation**

```python
preview_dir = output_dir / f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
result = self.capture_service.capture_current_complaint_segments(self.config, preview_dir)
```

```python
target = CaptureTarget(index=processed_index, display_name=item.display_name, amount_label=item.amount_text)
destination_dir = build_capture_dir(run_dir, target)
result = self.capture_service.capture_current_complaint_segments(self.config, destination_dir)
```

```python
self._set_status(f"预览分段图已保存，共 {result.segment_count} 张：{result.output_dir}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.14 -m pytest -q tests/test_session.py tests/test_batch.py`
Expected: PASS

### Task 6: Update docs and remove long-image wording from the main README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the user-facing description**

Replace long-image wording with segmented screenshot wording, including preview and batch instructions.

- [ ] **Step 2: Run targeted verification**

Run: `py -3.14 -m pytest -q tests/test_capture_segments.py tests/test_capture_order.py tests/test_batch.py`
Expected: PASS

### Task 7: Final verification

**Files:**
- Modify: `app/wechat_complaint_tool/capture.py`
- Modify: `app/wechat_complaint_tool/automation.py`
- Modify: `app/wechat_complaint_tool/gui.py`
- Modify: `app/wechat_complaint_tool/session.py`
- Modify: `README.md`
- Create: `tests/test_capture_segments.py`

- [ ] **Step 1: Run the full test suite**

Run: `py -3.14 -m pytest -q`
Expected: PASS with all tests green

- [ ] **Step 2: Run import verification**

Run:

```powershell
@'
import sys
sys.path.insert(0, 'app')
import wechat_complaint_tool.capture
import wechat_complaint_tool.automation
import wechat_complaint_tool.gui
print('import-ok')
'@ | py -3.14 -
```

Expected: `import-ok`
