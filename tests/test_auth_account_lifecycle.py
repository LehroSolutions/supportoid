"""Credential changes and account state must invalidate persisted authority."""

import time

from src.app.auth import AuthService
from src.app.automation_store import AutomationStore


def _auth(tmp_path):
    store = AutomationStore(str(tmp_path / "auth.db"))
    auth = AuthService({}, automation_store=store)
    auth.create_or_update_user("operator", "initial-test-password", "admin")
    return auth, store


def test_password_reset_revokes_existing_session(tmp_path):
    auth, _ = _auth(tmp_path)
    token = auth.login("operator", "initial-test-password")
    assert token and auth.get_user(token).role == "admin"
    auth.create_or_update_user("operator", "replacement-test-password", "admin")
    assert auth.get_user(token) is None
    assert auth.login("operator", "initial-test-password") is None
    assert auth.login("operator", "replacement-test-password")


def test_role_change_revokes_existing_admin_session(tmp_path):
    auth, _ = _auth(tmp_path)
    token = auth.login("operator", "initial-test-password")
    auth.create_or_update_user("operator", "initial-test-password", "support")
    assert auth.get_user(token) is None
    replacement = auth.login("operator", "initial-test-password")
    assert auth.get_user(replacement).role == "support"


def test_disabled_account_cannot_login_or_use_existing_session(tmp_path):
    auth, store = _auth(tmp_path)
    auth.create_or_update_user("other", "other-test-password", "support")
    token = auth.login("operator", "initial-test-password")
    with store._connect() as conn:
        conn.execute("UPDATE users SET disabled_at = ? WHERE username = ?", (time.time(), "operator"))
    assert auth.login("operator", "initial-test-password") is None
    assert auth.get_user(token) is None


def test_persisted_session_survives_restart_and_logout_revokes_it(tmp_path):
    auth, store = _auth(tmp_path)
    token = auth.login("operator", "initial-test-password")
    restarted = AuthService({}, automation_store=AutomationStore(store.sqlite_path))
    assert restarted.get_user(token).username == "operator"
    restarted.logout(token)
    assert auth.get_user(token) is None
