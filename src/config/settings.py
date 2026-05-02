"""SupportOID application settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _default_local_cors_origins() -> list[str]:
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ]


def _default_model_profiles() -> dict[str, dict[str, Any]]:
    return {
        "gpt-oss-remote": {
            "name": "gpt-oss-remote",
            "family": "gpt-oss",
            "provider": "openai-compatible",
            "base_url": "",
            "api_key": "",
            "model_id": "gpt-oss-120b",
            "transport": "responses",
            "enabled": True,
            "priority": 1,
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "supports_structured_output": True,
            "cost_score": 20,
            "power_score": 98,
            "capabilities": ["chat", "support", "grounded", "reasoning"],
            "rate_limit_rpm": 120,
        },
        "gemma4-remote": {
            "name": "gemma4-remote",
            "family": "gemma4",
            "provider": "openai-compatible",
            "base_url": "",
            "api_key": "",
            "model_id": "gemma-4",
            "transport": "chat_completions",
            "enabled": False,
            "priority": 2,
            "reasoning_effort": "medium",
            "max_tokens": 8192,
            "supports_structured_output": True,
            "cost_score": 18,
            "power_score": 92,
            "capabilities": ["chat", "support", "grounded"],
            "rate_limit_rpm": 120,
        },
        "gpt-oss-local": {
            "name": "gpt-oss-local",
            "family": "gpt-oss",
            "provider": "openai-compatible",
            "base_url": "",
            "api_key": "",
            "model_id": "gpt-oss-20b",
            "transport": "responses",
            "enabled": True,
            "priority": 3,
            "reasoning_effort": "medium",
            "max_tokens": 4096,
            "supports_structured_output": True,
            "cost_score": 8,
            "power_score": 87,
            "capabilities": ["chat", "support", "grounded", "local"],
            "rate_limit_rpm": 240,
        },
        "gemma4-local": {
            "name": "gemma4-local",
            "family": "gemma4",
            "provider": "openai-compatible",
            "base_url": "",
            "api_key": "",
            "model_id": "gemma-4",
            "transport": "chat_completions",
            "enabled": False,
            "priority": 4,
            "reasoning_effort": "medium",
            "max_tokens": 4096,
            "supports_structured_output": True,
            "cost_score": 7,
            "power_score": 82,
            "capabilities": ["chat", "support", "grounded", "local"],
            "rate_limit_rpm": 240,
        },
    }


def _default_model_chain() -> list[str]:
    return [
        "gpt-oss-remote",
        "gemma4-remote",
        "gpt-oss-local",
        "gemma4-local",
    ]


def _normalize_models(raw: Any) -> dict[str, dict[str, Any]]:
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                items.append((str(item["name"]), item))
    else:
        items = []

    normalized: dict[str, dict[str, Any]] = {}
    for key, value in items:
        if not isinstance(value, dict):
            continue
        profile = dict(value)
        profile["name"] = str(profile.get("name") or key)
        normalized[str(key)] = profile
    return normalized


@dataclass
class Settings:
    """Configuration for the SupportOID multi-agent system."""

    # Directories
    seed_dir: str = "./data/seed"
    model_dir: str = "./data/runtime/models"
    kb_dir: str = "./data/runtime/knowledge"
    feedback_dir: str = "./data/runtime/feedback"
    training_dir: str = "./data/runtime/training"
    cost_dir: str = "./data/runtime/costs"
    trace_dir: str = "./data/runtime/traces"
    sqlite_path: str = "./data/runtime/app/supportoid.db"
    seed_demo_kb_on_empty: bool = False

    # Retention
    trace_retention_days: int = 30
    feedback_retention_days: int = 90

    # Model behavior thresholds
    confidence_threshold: float = 0.5
    escalation_sentiment_threshold: float = -0.7
    min_feedback_for_retrain: int = 10
    retrain_interval_seconds: int = 3600

    # LLM runtime
    llm_api_key: str = ""
    llm_model: str = "gpt-oss-120b"
    llm_endpoint: str = ""
    llm_timeout_ms: int = 15000

    # Convex adapter bridge
    convex_adapter_url: str = ""
    convex_api_key: str = ""

    # Multi-model runtime registry
    models: dict = field(
        default_factory=_default_model_profiles
    )
    model_chain: list[str] = field(default_factory=_default_model_chain)
    default_model: str = "gpt-oss-remote"

    # Voice output
    voice: dict = field(
        default_factory=lambda: {
            "engine": "none",
            "format": "wav",
            "persona": "support",
            "personaplex_api_key": "",
            "personaplex_local_endpoint": "http://localhost:8080",
        }
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = field(default_factory=_default_local_cors_origins)

    # Auth / RBAC
    session_cookie_name: str = "supportoid_session"
    session_ttl_seconds: int = 12 * 60 * 60
    allow_legacy_anonymous_api: bool = False
    agent_token_ttl_seconds: int = 30 * 24 * 60 * 60
    auth_users: dict = field(default_factory=dict)

    # Deployment profile
    deployment_profile: str = "docker"

    def ensure_runtime_dirs(self) -> None:
        runtime_paths = [
            Path(self.seed_dir),
            Path(self.model_dir),
            Path(self.kb_dir),
            Path(self.feedback_dir),
            Path(self.training_dir),
            Path(self.cost_dir),
            Path(self.trace_dir),
            Path(self.sqlite_path).parent,
        ]
        for path in runtime_paths:
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment with sane defaults."""
        settings = cls()
        settings.host = os.getenv("SUPPORTOID_HOST", settings.host)
        settings.port = int(os.getenv("SUPPORTOID_PORT", settings.port))
        settings.llm_api_key = os.getenv("SUPPORTOID_LLM_API_KEY", settings.llm_api_key)
        settings.llm_model = os.getenv("SUPPORTOID_LLM_MODEL", settings.llm_model)
        settings.llm_endpoint = os.getenv("SUPPORTOID_LLM_ENDPOINT", settings.llm_endpoint)
        settings.llm_timeout_ms = int(
            os.getenv("SUPPORTOID_LLM_TIMEOUT_MS", settings.llm_timeout_ms)
        )
        settings.seed_dir = os.getenv("SUPPORTOID_SEED_DIR", settings.seed_dir)
        seed_demo_kb_raw = os.getenv("SUPPORTOID_SEED_DEMO_KB_ON_EMPTY", "").strip().lower()
        if seed_demo_kb_raw:
            settings.seed_demo_kb_on_empty = seed_demo_kb_raw in {
                "1",
                "true",
                "yes",
                "on",
            }
        settings.convex_adapter_url = os.getenv(
            "SUPPORTOID_CONVEX_ADAPTER_URL", settings.convex_adapter_url
        )
        settings.convex_api_key = os.getenv("SUPPORTOID_CONVEX_API_KEY", settings.convex_api_key)
        settings.sqlite_path = os.getenv("SUPPORTOID_SQLITE_PATH", settings.sqlite_path)
        settings.model_dir = os.getenv("SUPPORTOID_MODEL_DIR", settings.model_dir)
        settings.kb_dir = os.getenv("SUPPORTOID_KB_DIR", settings.kb_dir)
        settings.feedback_dir = os.getenv("SUPPORTOID_FEEDBACK_DIR", settings.feedback_dir)
        settings.training_dir = os.getenv("SUPPORTOID_TRAINING_DIR", settings.training_dir)
        settings.cost_dir = os.getenv("SUPPORTOID_COST_DIR", settings.cost_dir)
        settings.trace_dir = os.getenv("SUPPORTOID_TRACE_DIR", settings.trace_dir)
        settings.deployment_profile = os.getenv(
            "SUPPORTOID_DEPLOYMENT_PROFILE", settings.deployment_profile
        )
        settings.trace_retention_days = int(
            os.getenv(
                "SUPPORTOID_TRACE_RETENTION_DAYS",
                settings.trace_retention_days,
            )
        )
        settings.feedback_retention_days = int(
            os.getenv(
                "SUPPORTOID_FEEDBACK_RETENTION_DAYS",
                settings.feedback_retention_days,
            )
        )
        cors_raw = os.getenv("SUPPORTOID_CORS_ORIGINS", "").strip()
        if cors_raw:
            settings.cors_origins = [
                item.strip() for item in cors_raw.split(",") if item.strip()
            ]
        elif settings.deployment_profile.lower() in {
            "local",
            "dev",
            "development",
            "test",
        }:
            settings.cors_origins = _default_local_cors_origins()
        else:
            settings.cors_origins = []

        legacy_anon_raw = os.getenv("SUPPORTOID_ALLOW_LEGACY_ANON", "").strip().lower()
        settings.allow_legacy_anonymous_api = legacy_anon_raw in {
            "1",
            "true",
            "yes",
            "on",
        }

        settings.agent_token_ttl_seconds = int(
            os.getenv(
                "SUPPORTOID_AGENT_TOKEN_TTL_SECONDS",
                settings.agent_token_ttl_seconds,
            )
        )

        chain_raw = os.getenv("SUPPORTOID_MODEL_CHAIN", "").strip()
        if chain_raw:
            settings.model_chain = [
                item.strip() for item in chain_raw.split(",") if item.strip()
            ]

        models_raw = os.getenv("SUPPORTOID_MODELS_JSON", "").strip()
        if models_raw:
            parsed = json.loads(models_raw)
            merged = dict(settings.models)
            merged.update(_normalize_models(parsed))
            settings.models = merged

        auth_users_raw = os.getenv("SUPPORTOID_AUTH_USERS_JSON", "").strip()
        if auth_users_raw:
            parsed_users = json.loads(auth_users_raw)
            if isinstance(parsed_users, dict):
                settings.auth_users = parsed_users

        primary_profile = settings.models.get("gpt-oss-remote")
        if primary_profile:
            if settings.llm_endpoint and not primary_profile.get("base_url"):
                primary_profile["base_url"] = settings.llm_endpoint
            if settings.llm_api_key and not primary_profile.get("api_key"):
                primary_profile["api_key"] = settings.llm_api_key
            if settings.llm_model and not os.getenv("SUPPORTOID_MODELS_JSON", "").strip():
                primary_profile["model_id"] = settings.llm_model

        settings.ensure_runtime_dirs()
        return settings
