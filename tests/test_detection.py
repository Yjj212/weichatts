from wechat_complaint_tool.detection import DetectionCandidate, cluster_detection_rows


def test_cluster_detection_rows_groups_text_by_vertical_position() -> None:
    candidates = [
        DetectionCandidate("PingAn", (10, 10, 100, 30)),
        DetectionCandidate("59.97", (210, 12, 300, 30)),
        DetectionCandidate("processed", (10, 38, 110, 55)),
        DetectionCandidate("ShanShui", (10, 100, 100, 125)),
        DetectionCandidate("29.80", (210, 102, 300, 126)),
    ]

    rows = cluster_detection_rows(candidates, row_gap=18)

    assert len(rows) == 2
    assert rows[0].primary_text == "PingAn"
    assert rows[0].amount_text == "59.97"
    assert rows[1].primary_text == "ShanShui"


def test_cluster_detection_rows_builds_stable_fingerprint() -> None:
    candidates = [
        DetectionCandidate("PingAn", (10, 10, 100, 30)),
        DetectionCandidate("59.97", (210, 12, 300, 30)),
        DetectionCandidate("Refunded", (10, 38, 110, 55)),
    ]

    row = cluster_detection_rows(candidates, row_gap=18)[0]

    assert row.fingerprint == "PingAn|59.97|Refunded"


def test_cluster_detection_rows_merges_split_preview_row_into_same_customer() -> None:
    candidates = [
        DetectionCandidate("Alice", (40, 10, 120, 28)),
        DetectionCandidate("[processed]", (40, 34, 160, 52)),
        DetectionCandidate("processed", (80, 82, 160, 100)),
        DetectionCandidate("Internet service phone", (170, 82, 360, 100)),
        DetectionCandidate("29.80", (370, 82, 430, 100)),
        DetectionCandidate("Bob", (40, 132, 110, 150)),
        DetectionCandidate("[refunded]", (40, 156, 150, 174)),
        DetectionCandidate("refunded", (80, 204, 160, 222)),
        DetectionCandidate("Internet service phone", (170, 204, 360, 222)),
        DetectionCandidate("39.80", (370, 204, 430, 222)),
    ]

    rows = cluster_detection_rows(candidates, row_gap=18)

    assert len(rows) == 2
    assert rows[0].primary_text == "Alice"
    assert rows[0].amount_text == "29.80"
    assert "Internet service phone" in (rows[0].preview_text or "")
    assert rows[1].primary_text == "Bob"
    assert rows[1].amount_text == "39.80"
