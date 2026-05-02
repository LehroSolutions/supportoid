"""API contract tests for SupportOID v1 routes and compatibility aliases."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config.settings import Settings
from src.main import create_app


def _settings(root) -> Settings:
    return Settings(
        model_dir=str(root / "models"),
        kb_dir=str(root / "knowledge"),
        feedback_dir=str(root / "feedback"),
        training_dir=str(root / "training"),
        cost_dir=str(root / "costs"),
        trace_dir=str(root / "traces"),
        sqlite_path=str(root / "app.db"),
        allow_legacy_anonymous_api=False,
        deployment_profile="test",
        seed_demo_kb_on_empty=True,
        auth_users={"admin": {"password": "admin123", "role": "admin"}},
    )


@pytest.fixture()
def settings(tmp_path):
    return _settings(tmp_path / "api")


def test_v1_login_chat_feedback_and_stats(settings):
    app = create_app(settings)
    client = TestClient(app)

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    assert login.json()["ok"] is True

    chat = client.post("/api/v1/chat", json={"message": "How do I reset my password?"})
    assert chat.status_code == 200
    payload = chat.json()
    assert "conversation_id" in payload
    assert "response" in payload
    conversation_id = payload["conversation_id"]

    feedback = client.post(
        "/api/v1/feedback",
        json={
            "conversation_id": conversation_id,
            "rating": 5,
            "feedback_text": "Great",
            "corrected_intent": "",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "recorded"

    stats = client.get("/api/v1/stats")
    assert stats.status_code == 200
    assert "total_processed" in stats.json()


def test_legacy_aliases_emit_deprecation_headers(settings):
    app = create_app(settings)
    client = TestClient(app)

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    assert login.json()["ok"] is True

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers.get("Deprecation") == "true"
    assert "successor-version" in (health.headers.get("Link") or "")

    chat = client.post("/api/chat", json={"message": "Billing help"})
    assert chat.status_code == 200
    assert chat.headers.get("Deprecation") == "true"
