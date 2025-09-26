from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from spanish_vibes.app import app  # noqa: E402  (import after sys.path update)


def test_root_route_returns_success() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Spanish Vibes" in response.text
