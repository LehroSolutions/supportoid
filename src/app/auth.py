"""Session auth and RBAC helpers for SupportOID."""

from __future__ import annotations

import logging
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Dict, Iterable, Optional

from fastapi import Depends, HTTPException, Request, status

logger = logging.getLogger("supportoid.auth")

if TYPE_CHECKING:
    from src.app.automation_store import AutomationStore

try:
    import bcrypt as _bcrypt

    _BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None
    _BCRYPT_AVAILABLE = False


def _hash_password(password: str) -> str:
    if not _BCRYPT_AVAILABLE:
        raise RuntimeError("bcrypt is required for password hashing")
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=12)).decode()


def _is_bcrypt_hash(value: str) -> bool:
    return (
        value.startswith("$2b$") or value.startswith("$2a$") or value.startswith("$2y$")
    )


@dataclass
class UserContext:
    username: str
    role: str


@dataclass
class ServiceAccountContext:
    account_id: str
    name: str
    role: str
    scopes: list[str]


@dataclass
class AutomationPrincipal:
    principal_id: str
    principal_type: str
    display_name: str
    role: str
    scopes: list[str]

    def has_scopes(self, required: Iterable[str]) -> bool:
        current = set(self.scopes)
        return "*" in current or set(required).issubset(current)


ROLE_SCOPES: dict[str, list[str]] = {
    "support": [
        "chat:write",
        "feedback:write",
        "traces:read",
        "trace:read",
        "health:read",
        "jobs:read",
    ],
    "analyst": [
        "traces:read",
        "trace:read",
        "stats:read",
        "costs:read",
        "kb:read",
        "health:read",
        "jobs:read",
    ],
    "admin": ["*"],
}

SERVICE_ACCOUNT_ROLE_SCOPES: dict[str, list[str]] = {
    "support": list(ROLE_SCOPES["support"]),
    "analyst": list(ROLE_SCOPES["analyst"]),
    "admin": [
        "*",
        "chat:write",
        "feedback:write",
        "traces:read",
        "trace:read",
        "stats:read",
        "costs:read",
        "kb:read",
        "health:read",
        "jobs:read",
        "sync:run",
        "migrate:run",
        "cache:clear",
        "memory:cleanup",
        "approvals:manage",
        "service_accounts:read",
        "service_accounts:write",
    ],
}


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: Dict[str, list[float]] = defaultdict(list)

    def _active_attempts(self, username: str) -> list[float]:
        now = time.time()
        cutoff = now - self._window_seconds
        active = [t for t in self._attempts[username] if t > cutoff]
        self._attempts[username] = active
        return active

    def check(self, username: str) -> bool:
        return len(self._active_attempts(username)) < self._max_attempts

    def remaining_attempts(self, username: str) -> int:
        active = len(self._active_attempts(username))
        return max(0, self._max_attempts - active)

    def record_failure(self, username: str) -> None:
        self._active_attempts(username)
        self._attempts[username].append(time.time())

    def reset(self, username: str) -> None:
        self._attempts.pop(username, None)

    @property
    def stats(self) -> dict:
        now = time.time()
        active = sum(
            1
            for attempts in self._attempts.values()
            if any(t > now - self._window_seconds for t in attempts)
        )
        return {
            "tracked_users": len(self._attempts),
            "active_limited": active,
            "max_attempts": self._max_attempts,
            "window_seconds": self._window_seconds,
        }


class AuthService:
    """Persistent session auth with bcrypt password hashing, rate limiting, and RBAC."""

    def __init__(
        self,
        users: Dict[str, Dict[str, str]],
        session_ttl_seconds: int = 12 * 60 * 60,
        cookie_name: str = "supportoid_session",
        secure_cookies: bool = False,
        automation_store: "AutomationStore | None" = None,
        agent_token_ttl_seconds: int = 30 * 24 * 60 * 60,
        allow_password_fallback: bool = False,
    ):
        if not _BCRYPT_AVAILABLE and not allow_password_fallback:
            raise RuntimeError(
                "bcrypt is required outside tests. Install runtime dependencies before starting SupportOID."
            )

        self._session_ttl = session_ttl_seconds
        self.cookie_name = cookie_name
        self._secure_cookies = secure_cookies
        self._automation_store = automation_store
        self._agent_token_ttl_seconds = agent_token_ttl_seconds
        self._allow_password_fallback = allow_password_fallback
        self._login_limiter = LoginRateLimiter()
        self._users: Dict[str, Dict[str, str]] = {}

        self._seed_users(users)

    @property
    def secure_cookies(self) -> bool:
        return self._secure_cookies

    @property
    def login_rate_limiter(self) -> LoginRateLimiter:
        return self._login_limiter

    @property
    def session_ttl_seconds(self) -> int:
        return self._session_ttl

    def session_cookie_kwargs(self, token: str) -> dict:
        payload = {
            "key": self.cookie_name,
            "value": token,
            "httponly": True,
            "max_age": self._session_ttl,
            "samesite": "lax",
            "path": "/",
        }
        if self._secure_cookies:
            payload["secure"] = True
        return payload

    def session_cookie_delete_kwargs(self) -> dict:
        payload = {
            "key": self.cookie_name,
            "path": "/",
            "httponly": True,
            "samesite": "lax",
        }
        if self._secure_cookies:
            payload["secure"] = True
        return payload

    @property
    def bootstrap_hint(self) -> str:
        return (
            "No users have been provisioned yet. Run "
            "`python -m src.cli bootstrap-admin --username <name> --password <password>` "
            "before logging in."
        )

    @property
    def has_users(self) -> bool:
        if self._automation_store is not None:
            return self._automation_store.has_users()
        return bool(self._users)

    def _normalize_stored_password(self, password: str) -> str:
        if _is_bcrypt_hash(password):
            return password
        if _BCRYPT_AVAILABLE:
            return _hash_password(password)
        if self._allow_password_fallback:
            return password
        raise RuntimeError("bcrypt is required for password storage")

    def _seed_users(self, users: Dict[str, Dict[str, str]]) -> None:
        for username, data in users.items():
            password = str(data.get("password", "") or "")
            if not username or not password:
                continue
            role = str(data.get("role", "support") or "support")
            normalized_password = self._normalize_stored_password(password)
            if self._automation_store is not None:
                existing = self._automation_store.get_user(username)
                if existing is None:
                    self._automation_store.upsert_user(
                        username=username,
                        password_hash=normalized_password,
                        role=role,
                    )
            else:
                self._users[username] = {
                    "password": normalized_password,
                    "role": role,
                }

    def list_users(self) -> list[dict]:
        if self._automation_store is not None:
            return self._automation_store.list_users()
        return [
            {
                "username": username,
                "role": data.get("role", "support"),
                "password_hash": data.get("password", ""),
            }
            for username, data in self._users.items()
        ]

    def create_or_update_user(self, username: str, password: str, role: str) -> dict:
        normalized_password = self._normalize_stored_password(password)
        if self._automation_store is not None:
            return self._automation_store.upsert_user(
                username=username,
                password_hash=normalized_password,
                role=role,
            )
        self._users[username] = {"password": normalized_password, "role": role}
        return {"username": username, "role": role}

    def bootstrap_admin(self, username: str, password: str) -> dict:
        if self.has_users:
            raise ValueError("At least one user already exists. Use a managed user workflow instead.")
        return self.create_or_update_user(username=username, password=password, role="admin")

    def _lookup_user(self, username: str) -> Optional[dict]:
        if self._automation_store is not None:
            return self._automation_store.get_user(username)
        return self._users.get(username)

    def _verify_password(self, plain: str, stored: str) -> tuple[bool, bool]:
        if _is_bcrypt_hash(stored):
            if not _BCRYPT_AVAILABLE:
                return False, False
            try:
                return _bcrypt.checkpw(plain.encode(), stored.encode()), False
            except Exception:
                return False, False

        if _BCRYPT_AVAILABLE:
            # Legacy plaintext migration path for existing local databases.
            return plain == stored, True

        if self._allow_password_fallback:
            return plain == stored, False

        return False, False

    def login(
        self,
        username: str,
        password: str,
        *,
        user_agent: str = "",
        client_ip: str = "",
    ) -> Optional[str]:
        if not self.has_users:
            return None

        if not self._login_limiter.check(username):
            logger.warning("Login rate limited for user: %s", username)
            return None

        user = self._lookup_user(username)
        stored_password = ""
        role = "support"
        if user:
            stored_password = str(user.get("password_hash") or user.get("password") or "")
            role = str(user.get("role", "support") or "support")

        valid, needs_rehash = self._verify_password(password, stored_password)
        if not user or not valid:
            self._login_limiter.record_failure(username)
            return None

        if needs_rehash and self._automation_store is not None and _BCRYPT_AVAILABLE:
            self._automation_store.upsert_user(
                username=username,
                password_hash=_hash_password(password),
                role=role,
            )

        self._login_limiter.reset(username)
        token = secrets.token_urlsafe(32)

        if self._automation_store is not None:
            self._automation_store.delete_expired_sessions()
            self._automation_store.create_session(
                session_id=f"sess_{secrets.token_hex(12)}",
                token_hash=sha256(token.encode("utf-8")).hexdigest(),
                username=username,
                role=role,
                expires_at=time.time() + self._session_ttl,
                metadata={
                    "user_agent": str(user_agent or "")[:500],
                    "client_ip": str(client_ip or "")[:120],
                },
            )
            self._automation_store.record_user_login(username)

        logger.info("User logged in: %s (role=%s)", username, role)
        return token

    def logout(self, token: str) -> None:
        if not token:
            return
        if self._automation_store is not None:
            session = self._automation_store.revoke_session_by_token_hash(
                sha256(token.encode("utf-8")).hexdigest()
            )
            if session:
                logger.info("User logged out: %s", session.get("username"))

    def get_user(self, token: Optional[str]) -> Optional[UserContext]:
        if not token:
            return None
        if self._automation_store is not None:
            self._automation_store.delete_expired_sessions()
            session = self._automation_store.get_session_by_token_hash(
                sha256(token.encode("utf-8")).hexdigest()
            )
            if not session:
                return None
            return UserContext(
                username=str(session.get("username", "unknown")),
                role=str(session.get("role", "support")),
            )
        return None

    @property
    def active_session_count(self) -> int:
        if self._automation_store is None:
            return 0
        return len(self._automation_store.list_sessions())

    @property
    def active_sessions_list(self) -> list:
        if self._automation_store is None:
            return []
        sessions = self._automation_store.list_sessions()
        result = []
        for session in sessions:
            metadata = session.get("metadata") or {}
            result.append(
                {
                    "session_id": session.get("session_id", ""),
                    "username": session.get("username", "unknown"),
                    "role": session.get("role", "support"),
                    "created_at": session.get("created_at", 0),
                    "last_seen_at": session.get("last_seen_at", 0),
                    "expires_at": session.get("expires_at", 0),
                    "client_ip": metadata.get("client_ip", ""),
                    "user_agent": metadata.get("user_agent", ""),
                }
            )
        return result

    def create_service_account(
        self,
        name: str,
        role: str,
        scopes: list[str],
        description: str = "",
        expires_in_seconds: int | None = None,
    ) -> tuple[dict, str]:
        if self._automation_store is None:
            raise RuntimeError("Automation store is not configured")
        normalized_scopes = normalize_service_account_scopes(role, scopes)
        token = f"soid_sa_{secrets.token_urlsafe(32)}"
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        account_id = f"sa_{secrets.token_hex(8)}"
        ttl = expires_in_seconds or self._agent_token_ttl_seconds
        expires_at = time.time() + ttl if ttl else None
        record = self._automation_store.create_service_account(
            account_id=account_id,
            name=name,
            role=role,
            scopes=normalized_scopes,
            token_hash=token_hash,
            description=description,
            expires_at=expires_at,
        )
        return record, token

    def list_service_accounts(self, include_revoked: bool = True) -> list[dict]:
        if self._automation_store is None:
            return []
        return self._automation_store.list_service_accounts(include_revoked=include_revoked)

    def rotate_service_account(
        self,
        account_id: str,
        expires_in_seconds: int | None = None,
    ) -> tuple[dict, str] | None:
        if self._automation_store is None:
            return None
        token = f"soid_sa_{secrets.token_urlsafe(32)}"
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        ttl = expires_in_seconds or self._agent_token_ttl_seconds
        expires_at = time.time() + ttl if ttl else None
        record = self._automation_store.rotate_service_account(
            account_id=account_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        if record is None:
            return None
        return record, token

    def revoke_service_account(self, account_id: str) -> dict | None:
        if self._automation_store is None:
            return None
        return self._automation_store.revoke_service_account(account_id)

    def authenticate_service_account(
        self, token: str | None
    ) -> Optional[ServiceAccountContext]:
        if not token or self._automation_store is None:
            return None
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        record = self._automation_store.get_service_account_by_token_hash(token_hash)
        if not record:
            return None
        return ServiceAccountContext(
            account_id=record["account_id"],
            name=record["name"],
            role=record["role"],
            scopes=list(record.get("scopes", [])),
        )


def _read_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "").strip()
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    return token.strip()


def human_scopes_for_role(role: str) -> list[str]:
    return list(ROLE_SCOPES.get(role, []))


def service_account_scopes_for_role(role: str) -> list[str]:
    return list(SERVICE_ACCOUNT_ROLE_SCOPES.get(role, []))


def normalize_service_account_scopes(
    role: str, scopes: Iterable[str] | None
) -> list[str]:
    allowed = set(service_account_scopes_for_role(role))
    if not allowed:
        raise ValueError(f"Unsupported role: {role}")

    requested = [scope for scope in (scopes or []) if scope]
    if not requested:
        return ["*"] if role == "admin" else sorted(allowed)

    if role == "admin" and "*" in requested:
        return ["*"]

    if not set(requested).issubset(allowed):
        raise ValueError("Requested scopes are not allowed for the selected role")

    return sorted(dict.fromkeys(requested))


def to_automation_principal(
    *,
    user: UserContext | None = None,
    service_account: ServiceAccountContext | None = None,
    local: bool = False,
) -> AutomationPrincipal:
    if local:
        return AutomationPrincipal(
            principal_id="local-system",
            principal_type="local",
            display_name="local-system",
            role="admin",
            scopes=["*"],
        )
    if service_account is not None:
        return AutomationPrincipal(
            principal_id=service_account.account_id,
            principal_type="service_account",
            display_name=service_account.name,
            role=service_account.role,
            scopes=list(service_account.scopes),
        )
    if user is None:
        raise ValueError("A user or service account principal is required")
    return AutomationPrincipal(
        principal_id=user.username,
        principal_type="user",
        display_name=user.username,
        role=user.role,
        scopes=human_scopes_for_role(user.role),
    )


def get_current_user(request: Request) -> UserContext:
    auth: AuthService = request.app.state.auth
    token = request.cookies.get(auth.cookie_name)
    user = auth.get_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    def _dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Role cannot access this endpoint",
            )
        return user

    return _dependency


def has_role(user: UserContext, roles: Iterable[str]) -> bool:
    return user.role in set(roles)


def get_service_account_principal(request: Request) -> AutomationPrincipal:
    auth: AuthService = request.app.state.auth
    token = _read_bearer_token(request)
    principal = auth.authenticate_service_account(token)
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service account authentication required",
        )
    return to_automation_principal(service_account=principal)


def get_management_principal(request: Request) -> AutomationPrincipal:
    auth: AuthService = request.app.state.auth
    token = _read_bearer_token(request)
    if token:
        service_account = auth.authenticate_service_account(token)
        if not service_account:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            )
        return to_automation_principal(service_account=service_account)

    user = get_current_user(request)
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return to_automation_principal(user=user)
