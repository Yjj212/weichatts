from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

DEFAULT_ENABLED_EXPORT_FIELDS = {
    "transaction_amount",
    "transaction_time",
    "consultation_reason",
    "inquiry_time",
    "problem_description",
}


@dataclass(slots=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(slots=True)
class AppConfig:
    window_title_hint: str = "微信"
    output_dir: str = "image"
    wechat_window_rect: Rect | None = None
    list_region: Rect | None = None
    content_region: Rect | None = None
    scroll_settle_ms: int = 900
    chat_scroll_clicks: int = 2
    list_page_scroll_ratio: float = 0.85
    capture_overlap_threshold: float = 0.98
    enabled_export_fields: set[str] | None = None

    def __post_init__(self) -> None:
        if self.enabled_export_fields is None:
            self.enabled_export_fields = set(DEFAULT_ENABLED_EXPORT_FIELDS)


def config_path(base_dir: Path) -> Path:
    return base_dir / "config.json"


def load_config(base_dir: Path) -> AppConfig:
    path = config_path(base_dir)
    if not path.exists():
        return AppConfig()

    data = json.loads(path.read_text(encoding="utf-8"))
    enabled_export_fields = data.get("enabled_export_fields")
    if enabled_export_fields is None:
        enabled_export_fields = DEFAULT_ENABLED_EXPORT_FIELDS
    return AppConfig(
        window_title_hint=data.get("window_title_hint", "微信"),
        output_dir=data.get("output_dir", "image"),
        wechat_window_rect=_rect_from_dict(data.get("wechat_window_rect")),
        list_region=_rect_from_dict(data.get("list_region")),
        content_region=_rect_from_dict(
            data.get("content_region")
            or data.get("scroll_content_region")
            or data.get("right_panel_region")
            or data.get("chat_region")
        ),
        scroll_settle_ms=int(data.get("scroll_settle_ms", data.get("settle_delay_ms", 900))),
        chat_scroll_clicks=int(data.get("chat_scroll_clicks", 2)),
        list_page_scroll_ratio=float(data.get("list_page_scroll_ratio", 0.85)),
        capture_overlap_threshold=float(data.get("capture_overlap_threshold", 0.98)),
        enabled_export_fields=set(enabled_export_fields),
    )


def save_config(base_dir: Path, config: AppConfig) -> None:
    path = config_path(base_dir)
    payload = asdict(config)
    payload["enabled_export_fields"] = sorted(config.enabled_export_fields or [])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rect_from_dict(value: dict | None) -> Rect | None:
    if not value:
        return None
    return Rect(
        left=int(value["left"]),
        top=int(value["top"]),
        width=int(value["width"]),
        height=int(value["height"]),
    )
