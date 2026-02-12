from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_application


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app, _, _ = create_application(
        log_dir=str(tmp_path / "logs"),
        dataset_dir=str(tmp_path / "datasets"),
    )
    with TestClient(app) as test_client:
        yield test_client
