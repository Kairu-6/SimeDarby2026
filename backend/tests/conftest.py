import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.sqlite3"))
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "push_notifications_enabled", False)
    with TestClient(app) as instance:
        yield instance
