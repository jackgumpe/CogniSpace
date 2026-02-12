from __future__ import annotations

from threading import RLock

from app.models.dataset import JsonicDatasetRecord


class DatasetRegistry:
    """Thread-safe in-memory registry for built dataset metadata."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, JsonicDatasetRecord] = {}

    def save(self, record: JsonicDatasetRecord) -> JsonicDatasetRecord:
        with self._lock:
            self._records[record.dataset_id] = record
            return record.model_copy(deep=True)

    def get(self, dataset_id: str) -> JsonicDatasetRecord | None:
        with self._lock:
            record = self._records.get(dataset_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def require(self, dataset_id: str) -> JsonicDatasetRecord:
        record = self.get(dataset_id)
        if record is None:
            raise KeyError(f"dataset not found: {dataset_id}")
        return record
