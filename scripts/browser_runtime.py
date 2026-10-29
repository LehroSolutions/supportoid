"""Start isolated local services for the built frontend's browser regression."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

from tests.test_adapter_runtime import adapter, _port
from src.app.auth import AuthService
from src.app.automation_store import AutomationStore

root = Path(__file__).resolve().parents[1]
directory = Path(sys.argv[1]).resolve()
directory.mkdir(parents=True, exist_ok=True)
env = {**os.environ, "SUPPORTOID_DEPLOYMENT_PROFILE": "local", "SUPPORTOID_SQLITE_PATH": str(directory / "app.db"), "SUPPORTOID_AUTH_USERS_JSON": "{}", "SUPPORTOID_LLM_ENDPOINT": "", "SUPPORTOID_LLM_API_KEY": "", "SUPPORTOID_SEED_DEMO_KB_ON_EMPTY": "true", "SUPPORTOID_MODELS_JSON": json.dumps({name: {"enabled": False} for name in ["gpt-oss-remote", "gpt-oss-local", "gemma4-remote", "gemma4-local"]})}
for name in ["MODEL", "KB", "FEEDBACK", "TRAINING", "COST", "TRACE"]:
    env[f"SUPPORTOID_{name}_DIR"] = str(directory / name.lower())
bootstrap = subprocess.run([sys.executable, "-m", "src.cli", "bootstrap-admin", "--username", "browser-admin", "--password", "synthetic-browser-password"], cwd=root, env=env, capture_output=True, text=True, timeout=120)
if bootstrap.returncode:
    raise RuntimeError(bootstrap.stderr)
auth = AuthService({}, automation_store=AutomationStore(str(directory / "app.db")))
auth.create_or_update_user("browser-support", "synthetic-support-password", "support")
with adapter(directory / "adapter.json") as (_, adapter_url, adapter_headers):
    env["SUPPORTOID_CONVEX_ADAPTER_URL"] = adapter_url
    env["SUPPORTOID_CONVEX_API_KEY"] = adapter_headers["X-Adapter-Key"]
    port = _port()
    url = f"http://127.0.0.1:{port}"
    with (directory / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)], cwd=root, env=env, stdout=log, stderr=log)
        try:
            for _ in range(600):
                if server.poll() is not None:
                    raise RuntimeError((directory / "server.log").read_text())
                try:
                    if requests.get(url + "/api/v1/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError("Local runtime did not become ready")
            print(json.dumps({"url": url, "adapterUrl": adapter_url, "adapterHeaders": adapter_headers}), flush=True)
            sys.stdin.read()
        finally:
            if server.poll() is None:
                server.terminate()
                server.wait(timeout=15)
