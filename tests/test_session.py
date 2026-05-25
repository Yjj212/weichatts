from pathlib import Path

from wechat_complaint_tool.session import CaptureTarget, build_capture_dir, sanitize_name


def test_sanitize_name_replaces_invalid_characters() -> None:
    assert sanitize_name('  A:/B*?"<>|  ') == "A__B______"


def test_capture_folder_name_includes_index_name_and_amount() -> None:
    target = CaptureTarget(index=7, display_name="PingAn", amount_label="59.97")

    assert target.folder_name == "0007_PingAn_59.97"


def test_build_capture_dir_uses_target_folder_name_without_timestamp(tmp_path: Path) -> None:
    target = CaptureTarget(index=1, display_name="ShanShui")

    path = build_capture_dir(tmp_path, target)

    assert path == tmp_path / "0001_ShanShui"
