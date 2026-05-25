from PIL import Image, ImageDraw

from wechat_complaint_tool.stitching import LongImageComposer


def test_long_image_composer_returns_single_frame_unchanged() -> None:
    composer = LongImageComposer(overlap_threshold=0.98, minimum_overlap=20)
    frame = Image.new("RGB", (100, 160), (240, 240, 240))

    stitched = composer.compose([frame])

    assert stitched.size == (100, 160)


def test_long_image_composer_appends_new_content() -> None:
    composer = LongImageComposer(overlap_threshold=0.99, minimum_overlap=10)
    frame1 = Image.new("RGB", (80, 60))
    frame2 = Image.new("RGB", (80, 60))
    for y in range(60):
        for x in range(80):
            frame1.putpixel((x, y), (y, 0, 0))
            frame2.putpixel((x, y), (y + 30, 0, 0))

    stitched = composer.compose([frame1, frame2])

    assert stitched.height > 60


def test_long_image_composer_removes_duplicate_content() -> None:
    composer = LongImageComposer(overlap_threshold=0.99, minimum_overlap=10)
    frame = Image.new("RGB", (80, 60))
    for y in range(60):
        for x in range(80):
            frame.putpixel((x, y), (y, 0, 0))

    stitched = composer.compose([frame, frame])

    assert stitched.size == (80, 60)


def test_long_image_composer_ignores_edge_noise_when_detecting_overlap() -> None:
    composer = LongImageComposer(overlap_threshold=0.95, minimum_overlap=20)
    top = Image.new("RGB", (100, 80))
    bottom = Image.new("RGB", (100, 80))

    for y in range(80):
        for x in range(100):
            color_top = (y, x % 50, 0)
            top.putpixel((x, y), color_top)

    for y in range(80):
        source_y = y + 40
        for x in range(100):
            color_bottom = (source_y, x % 50, 0)
            bottom.putpixel((x, y), color_bottom)

    for y in range(80):
        for x in range(88, 100):
            top.putpixel((x, y), (255, 255, 255))
            bottom.putpixel((x, y), (0, 255, 0))

    stitched = composer.compose([top, bottom])

    assert stitched.width == 100
    assert 118 <= stitched.height <= 122


def test_long_image_composer_prefers_best_overlap_instead_of_first_match() -> None:
    composer = LongImageComposer(overlap_threshold=0.90, minimum_overlap=20)
    top = Image.new("RGB", (80, 100))
    bottom = Image.new("RGB", (80, 100))

    for y in range(100):
        for x in range(80):
            top.putpixel((x, y), ((y * 5 + x) % 255, (x * 7 + y) % 255, (y * 11) % 255))

    for y in range(100):
        source_y = y + 55
        for x in range(80):
            bottom.putpixel((x, y), ((source_y * 5 + x) % 255, (x * 7 + source_y) % 255, (source_y * 11) % 255))

    stitched = composer.compose([top, bottom])

    assert 153 <= stitched.height <= 157


def test_long_image_composer_resists_local_overlay_noise_on_short_conversation() -> None:
    composer = LongImageComposer(overlap_threshold=0.98, minimum_overlap=20)
    width = 220
    view_height = 160
    shift = 40

    canvas = Image.new("RGB", (width, view_height + shift), (242, 242, 242))
    draw = ImageDraw.Draw(canvas)
    for y, label in [(20, "HEAD"), (70, "BUBBLE1"), (120, "BUBBLE2"), (165, "TAIL")]:
        draw.rounded_rectangle((20, y, 180, y + 28), radius=10, fill=(255, 255, 255), outline=(230, 230, 230))
        draw.text((35, y + 8), label, fill=(0, 0, 0))

    frame1 = canvas.crop((0, 0, width, view_height))
    frame2 = canvas.crop((0, shift, width, shift + view_height))

    for x in range(180, 212):
        for y in range(78, 110):
            frame2.putpixel((x, y), (80, 200, 120))

    stitched = composer.compose([frame1, frame2])

    assert stitched.height == view_height + shift
