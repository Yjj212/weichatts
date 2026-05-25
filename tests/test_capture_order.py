from PIL import Image

from wechat_complaint_tool.capture import build_segment_file_name, crop_bottom_overlap, has_meaningful_new_content, normalize_bottom_origin_sequence


def test_build_segment_file_name_uses_three_digit_sequence() -> None:
    assert build_segment_file_name(1) == "001.png"
    assert build_segment_file_name(12) == "012.png"


def test_normalize_bottom_origin_sequence_keeps_bottom_first_order() -> None:
    collected = ["bottom", "middle", "top"]

    assert normalize_bottom_origin_sequence(collected) == ["bottom", "middle", "top"]


def test_crop_bottom_overlap_removes_repeated_bottom_band() -> None:
    previous = Image.new("RGB", (80, 120), (255, 255, 255))
    current = Image.new("RGB", (80, 120), (255, 255, 255))
    for y in range(60):
        for x in range(80):
            color = (y * 2, 0, 0)
            previous.putpixel((x, y), color)
            current.putpixel((x, y + 60), color)

    cropped, overlap = crop_bottom_overlap(previous=previous, current=current, minimum_overlap=20, threshold=0.98)

    assert overlap == 60
    assert cropped.height == 60


def test_has_meaningful_new_content_rejects_tiny_remainder() -> None:
    image = Image.new("RGB", (120, 18), (255, 255, 255))

    assert has_meaningful_new_content(image, minimum_height=24) is False
