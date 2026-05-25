from __future__ import annotations

from dataclasses import dataclass
import re


_AMOUNT_RE = re.compile(r"(?:[¥￥楼]?\s*)\d+(?:\.\d+)?")
_STATUS_RE = re.compile(r"^\s*[\[\(【]?(?:已处理完成|退款已到账|processed|refunded)")


@dataclass(slots=True)
class DetectionCandidate:
    text: str
    box: tuple[int, int, int, int]


@dataclass(slots=True)
class DetectionRow:
    primary_text: str
    amount_text: str | None
    preview_text: str | None
    center: tuple[int, int]
    top: int
    bottom: int

    @property
    def fingerprint(self) -> str:
        return f"{self.primary_text}|{self.amount_text or ''}|{self.preview_text or ''}"


def cluster_detection_rows(candidates: list[DetectionCandidate], row_gap: int = 18) -> list[DetectionRow]:
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda item: (item.box[1], item.box[0]))
    clusters: list[list[DetectionCandidate]] = []
    current: list[DetectionCandidate] = [ordered[0]]
    current_bottom = ordered[0].box[3]

    for candidate in ordered[1:]:
        candidate_top = candidate.box[1]
        previous_top = current[-1].box[1]
        vertical_gap = candidate_top - current_bottom

        if vertical_gap <= row_gap or _should_merge_split_row(current, candidate, vertical_gap, previous_top):
            current.append(candidate)
            current_bottom = max(current_bottom, candidate.box[3])
        else:
            clusters.append(current)
            current = [candidate]
            current_bottom = candidate.box[3]
    clusters.append(current)

    rows: list[DetectionRow] = []
    for cluster in clusters:
        texts = sorted(cluster, key=lambda item: (item.box[1], item.box[0]))
        amount = next((item.text.strip() for item in texts if _looks_like_amount(item.text)), None)
        amount_sources = {item.text.strip() for item in texts if _looks_like_amount(item.text)}

        primary_source = _choose_primary_source(texts)
        primary = primary_source.text.strip()
        preview = _choose_preview_text(texts, primary, amount_sources)

        left = min(item.box[0] for item in texts)
        right = max(item.box[2] for item in texts)
        top = min(item.box[1] for item in texts)
        bottom = max(item.box[3] for item in texts)
        rows.append(
            DetectionRow(
                primary_text=primary,
                amount_text=amount,
                preview_text=preview,
                center=((left + right) // 2, (top + bottom) // 2),
                top=top,
                bottom=bottom,
            )
        )
    return rows


def _should_merge_split_row(
    current_cluster: list[DetectionCandidate],
    candidate: DetectionCandidate,
    vertical_gap: int,
    previous_top: int,
) -> bool:
    if vertical_gap > 42:
        return False
    if candidate.box[1] - previous_top > 72:
        return False
    if _cluster_has_amount(current_cluster):
        return False
    if _looks_like_primary_name(candidate.text):
        return False
    return True


def _cluster_has_amount(cluster: list[DetectionCandidate]) -> bool:
    return any(_looks_like_amount(item.text) for item in cluster)


def _looks_like_amount(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return _AMOUNT_RE.fullmatch(stripped) is not None


def _looks_like_primary_name(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _looks_like_amount(stripped):
        return False
    if _STATUS_RE.search(stripped):
        return False
    if len(stripped) >= 14:
        return False
    if "服务" in stripped or "电话" in stripped:
        return False
    return True


def _choose_primary_source(texts: list[DetectionCandidate]) -> DetectionCandidate:
    for item in texts:
        if _looks_like_primary_name(item.text):
            return item
    non_amount = [item for item in texts if not _looks_like_amount(item.text)]
    return non_amount[0] if non_amount else texts[0]


def _choose_preview_text(texts: list[DetectionCandidate], primary: str, amount_sources: set[str]) -> str | None:
    preview_parts: list[str] = []
    for item in texts:
        stripped = item.text.strip()
        if not stripped or stripped == primary or stripped in amount_sources:
            continue
        preview_parts.append(stripped)
    if not preview_parts:
        return None
    return " ".join(preview_parts)
