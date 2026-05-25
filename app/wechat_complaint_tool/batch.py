from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DetectionItem:
    display_name: str
    amount_text: str | None
    preview_text: str | None
    click_point: tuple[int, int]
    fingerprint: str
    row_top: int = 0
    row_bottom: int = 0


@dataclass(slots=True)
class BatchPage:
    items: list[DetectionItem]

    def new_items(self, seen_fingerprints: set[str]) -> list[DetectionItem]:
        return [item for item in self.items if item.fingerprint not in seen_fingerprints]


@dataclass(slots=True)
class RunManifest:
    run_dir: Path
    entries: list[dict]
    failures: list[dict]


class BatchCoordinator:
    def __init__(self, manifest: RunManifest, max_empty_pages: int = 2, failure_pause_threshold: int = 3) -> None:
        self.manifest = manifest
        self.max_empty_pages = max_empty_pages
        self.failure_pause_threshold = failure_pause_threshold
        self.empty_page_count = 0
        self.consecutive_failures = 0
        self.seen_fingerprints: set[str] = set()
        self.seen_page_signatures: set[tuple[str, ...]] = set()

    def register_page(self, items: list[DetectionItem]) -> bool:
        page_signature = tuple(item.fingerprint for item in items)
        if page_signature and page_signature in self.seen_page_signatures:
            self.empty_page_count = self.max_empty_pages
            return True

        new_items = [item for item in items if item.fingerprint not in self.seen_fingerprints]
        if not new_items:
            self.empty_page_count += 1
            return self.empty_page_count >= self.max_empty_pages

        self.empty_page_count = 0
        if page_signature:
            self.seen_page_signatures.add(page_signature)
        for item in new_items:
            self.seen_fingerprints.add(item.fingerprint)
        return False

    def record_success(self, item: DetectionItem, output: Path | dict) -> None:
        self.consecutive_failures = 0
        if isinstance(output, Path):
            output_payload = {"output_path": str(output)}
        else:
            output_payload = output
        self.manifest.entries.append(
            {
                "display_name": item.display_name,
                "amount_text": item.amount_text,
                "preview_text": item.preview_text,
                "fingerprint": item.fingerprint,
                **output_payload,
            }
        )

    def record_failure(self, item_id: str, reason: str) -> bool:
        self.consecutive_failures += 1
        self.manifest.failures.append({"item_id": item_id, "reason": reason})
        return self.consecutive_failures >= self.failure_pause_threshold
