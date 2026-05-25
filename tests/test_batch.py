from pathlib import Path

from wechat_complaint_tool.batch import BatchCoordinator, BatchPage, DetectionItem, RunManifest
from wechat_complaint_tool.capture import chat_scroll_wheel_amount, list_scroll_wheel_amount


def test_batch_page_returns_only_new_items() -> None:
    page = BatchPage(
        items=[
            DetectionItem("平安是福", "¥59.97", "已处理完成", (10, 20), "a"),
            DetectionItem("山水之恋", "¥29.80", "已处理完成", (10, 70), "b"),
        ]
    )

    items = page.new_items({"a"})

    assert [item.fingerprint for item in items] == ["b"]


def test_coordinator_stops_after_two_empty_pages(tmp_path: Path) -> None:
    manifest = RunManifest(run_dir=tmp_path, entries=[], failures=[])
    coordinator = BatchCoordinator(manifest=manifest, max_empty_pages=2, failure_pause_threshold=3)

    assert coordinator.register_page([]) is False
    assert coordinator.register_page([]) is True


def test_coordinator_stops_immediately_when_same_page_repeats_without_new_items(tmp_path: Path) -> None:
    manifest = RunManifest(run_dir=tmp_path, entries=[], failures=[])
    coordinator = BatchCoordinator(manifest=manifest, max_empty_pages=2, failure_pause_threshold=3)
    items = [DetectionItem("Alice", "29.80", "preview", (10, 10), "alice|29.80|preview")]

    assert coordinator.register_page(items) is False
    assert coordinator.register_page(items) is True


def test_coordinator_records_failure_and_pauses_after_threshold(tmp_path: Path) -> None:
    manifest = RunManifest(run_dir=tmp_path, entries=[], failures=[])
    coordinator = BatchCoordinator(manifest=manifest, max_empty_pages=2, failure_pause_threshold=2)

    assert coordinator.record_failure("0001", "ocr failed") is False
    assert coordinator.record_failure("0002", "stitch failed") is True

    assert manifest.failures == [
        {"item_id": "0001", "reason": "ocr failed"},
        {"item_id": "0002", "reason": "stitch failed"},
    ]


def test_coordinator_records_output_dir_and_segment_count(tmp_path: Path) -> None:
    manifest = RunManifest(run_dir=tmp_path, entries=[], failures=[])
    coordinator = BatchCoordinator(manifest=manifest)
    item = DetectionItem("Alice", "39.80", "preview", (10, 10), "fp-1")

    coordinator.record_success(
        item,
        {
            "output_dir": str(tmp_path / "0001_Alice_39.80"),
            "segment_count": 3,
        },
    )

    assert manifest.entries == [
        {
            "display_name": "Alice",
            "amount_text": "39.80",
            "preview_text": "preview",
            "fingerprint": "fp-1",
            "output_dir": str(tmp_path / "0001_Alice_39.80"),
            "segment_count": 3,
        }
    ]


def test_scroll_wheel_amounts_respect_right_panel_reverse_and_left_panel_normal() -> None:
    assert chat_scroll_wheel_amount(4) == -480
    assert list_scroll_wheel_amount(8) == -960
