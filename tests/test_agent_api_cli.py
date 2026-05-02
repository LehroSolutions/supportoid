from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from src.cli.__main__ import EXIT_APPROVAL, EXIT_OK, main as cli_main
from src.config.settings import Settings
from src.main import create_app


def _settings(root: Path) -> Settings:
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
    return _settings(tmp_path / "agent")


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def _create_service_account(
    client: TestClient,
    *,
    name: str,
    role: str,
    scopes: list[str] | None = None,
) -> tuple[str, str]:
    response = client.post(
        "/api/v1/agent/service-accounts",
        json={
            "name": name,
            "role": role,
            "scopes": scopes or [],
            "description": f"{name} test account",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    result = payload["result"]
    return result["account_id"], result["token"]


def test_agent_service_account_lifecycle_and_auth_boundary(settings):
    app = create_app(settings)
    client = TestClient(app)
    _login_admin(client)

    account_id, token = _create_service_account(
        client,
        name=f"analyst-{uuid.uuid4().hex[:6]}",
        role="analyst",
    )

    cookie_only = client.get("/api/v1/agent/capabilities")
    assert cookie_only.status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    capabilities = client.get("/api/v1/agent/capabilities", headers=headers)
    assert capabilities.status_code == 200
    payload = capabilities.json()
    operation_ids = {item["operation_id"] for item in payload["result"]["items"]}
    assert "stats.get" in operation_ids
    assert "sync.run" not in operation_ids

    rotate = client.post(f"/api/v1/agent/service-accounts/{account_id}/rotate")
    assert rotate.status_code == 200
    new_token = rotate.json()["result"]["token"]

    old_token_response = client.get(
        "/api/v1/agent/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert old_token_response.status_code == 401

    new_token_response = client.get(
        "/api/v1/agent/capabilities",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert new_token_response.status_code == 200

    revoke = client.post(f"/api/v1/agent/service-accounts/{account_id}/revoke")
    assert revoke.status_code == 200

    revoked_token_response = client.get(
        "/api/v1/agent/capabilities",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert revoked_token_response.status_code == 401


def test_agent_invoke_idempotency_and_approval_jobs(settings):
    app = create_app(settings)
    client = TestClient(app)
    _login_admin(client)

    _, support_token = _create_service_account(
        client,
        name=f"support-{uuid.uuid4().hex[:6]}",
        role="support",
    )
    support_headers = {
        "Authorization": f"Bearer {support_token}",
        "Idempotency-Key": "idem-chat-1",
        "X-Request-ID": "req-chat-1",
    }
    chat_payload = {
        "operation_id": "chat.send",
        "input": {"message": "How do I reset my password?"},
    }
    first_chat = client.post(
        "/api/v1/agent/invoke",
        json=chat_payload,
        headers=support_headers,
    )
    second_chat = client.post(
        "/api/v1/agent/invoke",
        json=chat_payload,
        headers=support_headers,
    )
    assert first_chat.status_code == 200
    assert second_chat.status_code == 200
    assert first_chat.json()["result"]["conversation_id"] == second_chat.json()["result"]["conversation_id"]

    _, admin_token = _create_service_account(
        client,
        name=f"admin-{uuid.uuid4().hex[:6]}",
        role="admin",
        scopes=["sync:run", "jobs:read"],
    )
    admin_headers = {
        "Authorization": f"Bearer {admin_token}",
        "Idempotency-Key": "idem-sync-1",
        "X-Request-ID": "req-sync-1",
    }
    sync_payload = {
        "operation_id": "sync.run",
        "input": {"limit": 5},
    }
    sync_response = client.post(
        "/api/v1/agent/invoke",
        json=sync_payload,
        headers=admin_headers,
    )
    assert sync_response.status_code == 200
    sync_envelope = sync_response.json()
    assert sync_envelope["status"] == "approval_required"
    assert sync_envelope["approval_id"]
    assert sync_envelope["job_id"]

    jobs = client.get("/api/v1/agent/jobs", headers={"Authorization": f"Bearer {admin_token}"})
    assert jobs.status_code == 200
    statuses = {
        item["job_id"]: item["status"] for item in jobs.json()["result"]["items"]
    }
    assert statuses[sync_envelope["job_id"]] == "waiting_approval"

    approve = client.post(
        f"/api/v1/agent/approvals/{sync_envelope['approval_id']}/decision",
        json={"decision": "approve", "reason": "scheduled test"},
    )
    assert approve.status_code == 200
    approve_envelope = approve.json()
    assert approve_envelope["status"] == "completed"
    assert approve_envelope["job_id"] == sync_envelope["job_id"]

    job = client.get(
        f"/api/v1/agent/jobs/{sync_envelope['job_id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert job.status_code == 200
    assert job.json()["result"]["status"] == "completed"


def test_cli_local_agent_commands(capsys, monkeypatch, tmp_path):
    settings = _settings(tmp_path / "agent_cli_local")
    monkeypatch.setattr("src.cli.__main__.Settings.from_env", lambda: settings)

    exit_code = cli_main(["--json", "capabilities"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == EXIT_OK
    assert payload["status"] == "completed"

    exit_code = cli_main(
        [
            "--json",
            "--idempotency-key",
            "cli-chat-1",
            "invoke",
            "chat.send",
            "--input",
            '{"message":"Need help with billing"}',
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == EXIT_OK
    assert payload["status"] == "completed"
    assert payload["result"]["conversation_id"]

    exit_code = cli_main(
        [
            "--json",
            "--idempotency-key",
            "cli-sync-1",
            "invoke",
            "sync.run",
            "--input",
            '{"limit": 3}',
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == EXIT_APPROVAL
    assert payload["status"] == "approval_required"

    exit_code = cli_main(
        [
            "--json",
            "approve",
            payload["approval_id"],
            "--decision",
            "approve",
            "--reason",
            "local cli test",
        ]
    )
    captured = capsys.readouterr()
    approval_payload = json.loads(captured.out)
    assert exit_code == EXIT_OK
    assert approval_payload["status"] == "completed"


def test_cli_remote_agent_capabilities(capsys, monkeypatch, tmp_path):
    settings = _settings(tmp_path / "agent_remote")
    app = create_app(settings)
    _, token = app.state.auth.create_service_account(
        name=f"remote-{uuid.uuid4().hex[:6]}",
        role="support",
        scopes=["chat:write", "feedback:write", "health:read", "jobs:read"],
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.1)

    try:
        monkeypatch.setattr("src.cli.__main__.Settings.from_env", lambda: settings)
        exit_code = cli_main(
            [
                "--mode",
                "remote",
                "--base-url",
                f"http://127.0.0.1:{port}",
                "--token",
                token,
                "--json",
                "capabilities",
            ]
        )
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert exit_code == EXIT_OK
        assert payload["status"] == "completed"
        operation_ids = {item["operation_id"] for item in payload["result"]["items"]}
        assert "health.get" in operation_ids
        assert "sync.run" not in operation_ids
    finally:
        server.should_exit = True
        thread.join(timeout=10)
