"""Exercise the built adapter, including persistence across process restarts."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager

import requests


def _port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def adapter(database, *, ready=True):
    executable = os.environ.get("SUPPORTOID_TEST_NODE") or shutil.which("node")
    assert executable, "Node 24+ is required to verify the built adapter"
    entry = Path(__file__).resolve().parents[1] / "convex-adapter/dist/index.js"
    assert entry.is_file(), "Run bun run build:adapter before backend tests"
    port = _port()
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "NODE_ENV": "production", "ADAPTER_HOST": "127.0.0.1", "ADAPTER_PORT": str(port), "ADAPTER_DATA_FILE": str(database), "ADAPTER_API_KEY": "test-adapter-key-at-least-32-characters"}
    process = subprocess.Popen([executable, str(entry)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    headers = {"X-Adapter-Key": env["ADAPTER_API_KEY"]}
    try:
        if ready:
            for _ in range(300):
                assert process.poll() is None, process.communicate()[1].decode(errors="replace")
                try:
                    if requests.get(url + "/sync/health", headers=headers, timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Adapter did not become ready")
        yield process, url, headers
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        process.communicate()


def test_authenticated_sync_replay_and_restart(tmp_path):
    database = tmp_path / "adapter.json"
    event = {"eventId": "event-one", "entityType": "trace", "payload": {"session_id": "session-one", "message": "synthetic trace"}}
    with adapter(database) as (_, url, headers):
        assert requests.get(url + "/sync/health", timeout=2).status_code == 401
        assert requests.post(url + "/sync/event", json=event, headers=headers, timeout=2).status_code == 202
        reordered = {**event, "payload": {"message": "synthetic trace", "session_id": "session-one"}}
        assert requests.post(url + "/sync/event", json=reordered, headers=headers, timeout=2).status_code == 202
        assert requests.post(url + "/sync/event", json=event, headers=headers, timeout=2).status_code == 202
        conflict = {**event, "payload": {"session_id": "session-one", "message": "changed"}}
        assert requests.post(url + "/sync/event", json=conflict, headers=headers, timeout=2).status_code == 409
        assert requests.get(url + "/data/traces?limit=NaN", headers=headers, timeout=2).status_code == 400
        hostile = {**event, "eventId": "__proto__"}
        assert requests.post(url + "/sync/event", json=hostile, headers=headers, timeout=2).status_code == 400
        assert requests.get(url + "/data/traces/constructor", headers=headers, timeout=2).status_code == 404
    with adapter(database) as (_, url, headers):
        assert requests.get(url + "/data/traces/session-one", headers=headers, timeout=2).json() == event["payload"]
    assert len(json.loads(database.read_text())["events"]) == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_store_fails_closed_without_overwriting(tmp_path):
    database = tmp_path / "broken.json"
    database.write_text("not valid JSON")
    with adapter(database, ready=False) as (process, _, _):
        process.wait(timeout=30)
        assert process.returncode != 0
    assert database.read_text() == "not valid JSON"
