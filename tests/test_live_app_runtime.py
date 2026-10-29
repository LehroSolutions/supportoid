"""Boot the actual HTTP entry point against isolated files and the built adapter."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

from tests.test_adapter_runtime import adapter, _port


def test_live_bootstrap_login_chat_sync_logout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "SUPPORTOID_DEPLOYMENT_PROFILE": "local", "SUPPORTOID_SQLITE_PATH": str(tmp_path / "app.db"), "SUPPORTOID_AUTH_USERS_JSON": "{}", "SUPPORTOID_LLM_ENDPOINT": "", "SUPPORTOID_LLM_API_KEY": "", "SUPPORTOID_SEED_DEMO_KB_ON_EMPTY": "true", "SUPPORTOID_MODELS_JSON": json.dumps({"gpt-oss-remote": {"enabled": False}, "gpt-oss-local": {"enabled": False}, "gemma4-remote": {"enabled": False}, "gemma4-local": {"enabled": False}})}
    for name in ["MODEL", "KB", "FEEDBACK", "TRAINING", "COST", "TRACE"]:
        env[f"SUPPORTOID_{name}_DIR"] = str(tmp_path / name.lower())
    bootstrap = subprocess.run([sys.executable, "-m", "src.cli", "bootstrap-admin", "--username", "smoke-admin", "--password", "synthetic-test-password"], cwd=root, env=env, capture_output=True, text=True, timeout=90)
    assert bootstrap.returncode == 0, bootstrap.stderr
    with adapter(tmp_path / "adapter.json") as (_, adapter_url, adapter_headers):
        env["SUPPORTOID_CONVEX_ADAPTER_URL"] = adapter_url
        env["SUPPORTOID_CONVEX_API_KEY"] = adapter_headers["X-Adapter-Key"]
        base_url = f"http://127.0.0.1:{_port()}"
        port = base_url.rsplit(":", 1)[1]
        with (tmp_path / "server.log").open("w") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.main:create_app", "--factory", "--host", "127.0.0.1", "--port", port], cwd=root, env=env, stdout=log, stderr=log)
            try:
                client = requests.Session()
                for _ in range(600):
                    assert server.poll() is None, (tmp_path / "server.log").read_text()
                    try:
                        if client.get(base_url + "/api/v1/health", timeout=1).status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("HTTP application did not become ready")
                assert client.get(base_url + "/api/v1/auth/me", timeout=5).status_code == 401
                assert client.get(base_url + "/", timeout=5).status_code == 200
                headers = {"Origin": base_url, "X-CSRF-Token": client.cookies["csrf_token"]}
                login = client.post(base_url + "/api/v1/auth/login", json={"username": "smoke-admin", "password": "synthetic-test-password"}, headers=headers, timeout=10)
                assert login.status_code == 200 and login.json()["ok"]
                forged = client.post(base_url + "/api/v1/chat", json={"message": "forged"}, headers={"Origin": "https://untrusted.example"}, timeout=5)
                assert forged.status_code == 403
                chat = client.post(base_url + "/api/v1/chat", json={"message": "How do I reset my password?"}, headers=headers, timeout=15)
                assert chat.status_code == 200, chat.text
                assert chat.json()["response"]
                sync = client.post(base_url + "/api/v1/sync", json={"limit": 50}, headers=headers, timeout=15)
                assert sync.status_code == 200, sync.text
                remote = requests.get(adapter_url + "/data/traces", headers=adapter_headers, timeout=5).json()
                assert remote["traces"]
                assert client.post(base_url + "/api/v1/auth/logout", headers=headers, timeout=5).status_code == 200
                assert client.get(base_url + "/api/v1/auth/me", timeout=5).status_code == 401
                client.close()
            finally:
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=15)
