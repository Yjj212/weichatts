from pathlib import Path

from wechat_complaint_tool.config import AppConfig, Rect, load_config, save_config


def test_load_default_config_when_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path)

    assert config.window_title_hint == "微信"
    assert config.output_dir == "image"
    assert config.list_region is None
    assert config.content_region is None
    assert config.chat_scroll_clicks == 2
    assert "transaction_amount" in config.enabled_export_fields
    assert "problem_description" in config.enabled_export_fields


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    original = AppConfig(
        window_title_hint="WeChat",
        output_dir="exports",
        wechat_window_rect=Rect(0, 0, 800, 900),
        list_region=Rect(1, 2, 3, 4),
        content_region=Rect(5, 6, 7, 8),
        scroll_settle_ms=1200,
        list_page_scroll_ratio=0.85,
        capture_overlap_threshold=0.97,
        enabled_export_fields={"transaction_amount", "problem_description"},
    )

    save_config(tmp_path, original)
    restored = load_config(tmp_path)

    assert restored == original


def test_load_config_gracefully_handles_legacy_shape(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        """
        {
          "window_title_hint": "微信",
          "output_dir": "captures",
          "list_region": {"left": 1, "top": 2, "width": 3, "height": 4},
          "scroll_content_region": {"left": 5, "top": 6, "width": 7, "height": 8},
          "settle_delay_ms": 900
        }
        """,
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.list_region == Rect(1, 2, 3, 4)
    assert config.content_region == Rect(5, 6, 7, 8)
    assert config.scroll_settle_ms == 900
    assert "consultation_reason" in config.enabled_export_fields


def test_load_config_treats_null_enabled_export_fields_as_default(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        """
        {
          "enabled_export_fields": null
        }
        """,
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert "transaction_time" in config.enabled_export_fields
    assert "consultation_reason" in config.enabled_export_fields
