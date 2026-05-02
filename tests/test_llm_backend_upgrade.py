from __future__ import annotations

import uuid
from pathlib import Path

from src.agents.empathy import EmpathyEngine
from src.agents.llm_gateway import LLMGateway
from src.agents.support_response import SupportResponseEngine
from src.app.auth import AuthService
from src.app.dto import ChatRequest
from src.app.service import SupportOIDService
from src.app.storage import SQLiteStore
from src.config.settings import Settings
from src.orchestrator import Orchestrator


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _settings() -> Settings:
    root = Path("data") / "test_tmp" / f"llm_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        model_dir=str(root / "models"),
        kb_dir=str(root / "knowledge"),
        feedback_dir=str(root / "feedback"),
        training_dir=str(root / "training"),
        cost_dir=str(root / "costs"),
        trace_dir=str(root / "traces"),
        sqlite_path=str(root / "app.db"),
        deployment_profile="test",
        seed_demo_kb_on_empty=True,
    )
    settings.models["gpt-oss-remote"]["base_url"] = ""
    settings.models["gpt-oss-local"]["base_url"] = ""
    settings.models["gemma4-remote"]["base_url"] = ""
    settings.models["gemma4-local"]["base_url"] = ""
    return settings


def test_llm_gateway_responses_transport(monkeypatch):
    settings = _settings()
    settings.models["gpt-oss-remote"]["base_url"] = "http://llm.test"
    settings.model_chain = ["gpt-oss-remote"]

    import src.agents.llm_gateway as gateway_module

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/v1/responses")
        assert json["model"] == "gpt-oss-120b"
        return FakeResponse(
            {
                "id": "resp_1",
                "output": [
                    {
                        "content": [
                            {
                                "text": (
                                    '{"answer":"Use the reset password link on the sign-in page.",'
                                    '"confidence":0.82,"tone":"warm","needs_clarification":false,'
                                    '"should_escalate":false,"escalation_reason":"",'
                                    '"suggested_actions":["Collect account email"],'
                                    '"grounding_ids":["kb-001"]}'
                                )
                            }
                        ]
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 8},
            }
        )

    monkeypatch.setattr(gateway_module.requests, "post", fake_post)

    gateway = LLMGateway(settings)
    profile = gateway.ordered_profiles()[0]
    attempt = gateway.invoke_profile(
        profile,
        system_prompt="system",
        user_prompt="user",
        schema={"type": "object"},
    )
    assert attempt.ok is True
    assert attempt.input_tokens == 12
    assert attempt.payload["answer"].startswith("Use the reset")


def test_llm_gateway_chat_completions_transport(monkeypatch):
    settings = _settings()
    settings.models["gemma4-remote"]["base_url"] = "http://gemma.test"
    settings.models["gemma4-remote"]["enabled"] = True
    settings.model_chain = ["gemma4-remote"]

    import src.agents.llm_gateway as gateway_module

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/v1/chat/completions")
        assert json["model"] == "gemma-4"
        return FakeResponse(
            {
                "id": "chatcmpl_1",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer":"Please open Settings, then Billing, to review the charge.",'
                                '"confidence":0.71,"tone":"formal","needs_clarification":false,'
                                '"should_escalate":false,"escalation_reason":"",'
                                '"suggested_actions":["Review invoice"],'
                                '"grounding_ids":["kb-002"]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 6},
            }
        )

    monkeypatch.setattr(gateway_module.requests, "post", fake_post)

    gateway = LLMGateway(settings)
    profile = gateway.ordered_profiles()[0]
    attempt = gateway.invoke_profile(
        profile,
        system_prompt="system",
        user_prompt="user",
        schema={"type": "object"},
    )
    assert attempt.ok is True
    assert attempt.output_tokens == 6
    assert attempt.payload["tone"] == "formal"


def test_support_response_failsover_after_unsupported_action(monkeypatch):
    settings = _settings()
    settings.models["gpt-oss-remote"]["base_url"] = "http://llm.test"
    settings.models["gemma4-remote"]["base_url"] = "http://gemma.test"
    settings.models["gemma4-remote"]["enabled"] = True
    settings.model_chain = ["gpt-oss-remote", "gemma4-remote"]

    import src.agents.llm_gateway as gateway_module

    calls = {"count": 0}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(
                {
                    "id": "resp_bad",
                    "output": [
                        {
                            "content": [
                                {
                                    "text": (
                                        '{"answer":"I have already issued your refund and escalated the case.",'
                                        '"confidence":0.9,"tone":"warm","needs_clarification":false,'
                                        '"should_escalate":true,"escalation_reason":"billing",'
                                        '"suggested_actions":["Review refund"],'
                                        '"grounding_ids":["kb-003"]}'
                                    )
                                }
                            ]
                        }
                    ],
                    "usage": {"input_tokens": 11, "output_tokens": 7},
                }
            )
        return FakeResponse(
            {
                "id": "chat_good",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer":"I can help you prepare a refund review. Please share the plan, charge date, and amount.",'
                                '"confidence":0.66,"tone":"empathetic","needs_clarification":true,'
                                '"should_escalate":false,"escalation_reason":"",'
                                '"suggested_actions":["Collect refund details"],'
                                '"grounding_ids":["kb-003"]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 9},
            }
        )

    monkeypatch.setattr(gateway_module.requests, "post", fake_post)

    engine = SupportResponseEngine(settings)
    classification = {
        "intent": "refund_request",
        "confidence": 0.7,
        "sentiment": -0.2,
        "urgency": 0.4,
        "entities": {"amount": "29"},
    }
    empathy = EmpathyEngine().analyze(classification, [])
    kb_results = [
        {
            "id": "kb-003",
            "title": "Refund Policy",
            "content": "Refunds are reviewed within policy.",
            "_score": 42,
        }
    ]

    result = engine.generate(
        "I want my money back.",
        classification,
        empathy,
        kb_results,
        conversation_turns=[],
    )
    assert result.source == "llm:gemma4-remote"
    assert result.fallback_used is True
    assert "already issued" not in result.text.lower()


def test_support_response_safe_fallback_blocks_false_claims(monkeypatch):
    settings = _settings()
    settings.models["gpt-oss-remote"]["base_url"] = "http://llm.test"
    settings.model_chain = ["gpt-oss-remote"]

    import src.agents.llm_gateway as gateway_module

    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse(
            {
                "id": "resp_bad",
                "output": [
                    {
                        "content": [
                            {
                                "text": (
                                    '{"answer":"I have already created a high-priority ticket for you.",'
                                    '"confidence":0.8,"tone":"warm","needs_clarification":false,'
                                    '"should_escalate":true,"escalation_reason":"bug",'
                                    '"suggested_actions":["Wait for update"],'
                                    '"grounding_ids":[]}'
                                )
                            }
                        ]
                    }
                ],
                "usage": {"input_tokens": 8, "output_tokens": 5},
            }
        )

    monkeypatch.setattr(gateway_module.requests, "post", fake_post)

    engine = SupportResponseEngine(settings)
    classification = {
        "intent": "complaint",
        "confidence": 0.51,
        "sentiment": -0.7,
        "urgency": 0.5,
        "entities": {},
    }
    empathy = EmpathyEngine().analyze(classification, [])
    result = engine.generate(
        "This is unacceptable.",
        classification,
        empathy,
        [],
        conversation_turns=[],
    )
    assert result.source.startswith("fallback:")
    assert "already created" not in result.text.lower()


def test_orchestrator_persists_conversation_across_instances():
    settings = _settings()
    first = Orchestrator(settings)
    first.initialize()

    first.process("How do I reset my password?", conversation_id="persist_me")

    second = Orchestrator(settings)
    second.initialize()
    second.process("And if the email never arrives?", conversation_id="persist_me")

    store = SQLiteStore(settings.sqlite_path)
    turns = store.list_conversation_turns("persist_me", limit=10)
    assert len(turns) >= 4
    assert turns[0]["role"] == "user"
    assert turns[-1]["role"] == "agent"


def test_service_chat_reports_gemma_runtime(monkeypatch):
    settings = _settings()
    settings.models["gemma4-remote"]["base_url"] = "http://gemma.test"
    settings.models["gemma4-remote"]["enabled"] = True
    settings.model_chain = ["gemma4-remote"]

    import src.agents.llm_gateway as gateway_module

    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse(
            {
                "id": "chat_gemma",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer":"Please open the billing page to confirm the invoice details.",'
                                '"confidence":0.73,"tone":"formal","needs_clarification":false,'
                                '"should_escalate":false,"escalation_reason":"",'
                                '"suggested_actions":["Review invoice"],'
                                '"grounding_ids":["kb-002"]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 14, "completion_tokens": 10},
            }
        )

    monkeypatch.setattr(gateway_module.requests, "post", fake_post)

    service = SupportOIDService(settings)
    chat = service.chat(ChatRequest(message="Why was I billed?"), actor="support")
    assert chat.source == "llm:gemma4-remote"

    stats = service.get_stats_report()
    assert stats.active_model_profile == "gemma4-remote"
    assert stats.active_model_family == "gemma4"
    assert stats.llm_transport == "chat_completions"

    traces = service.list_trace_summaries(limit=5)
    assert traces
    detailed = service.get_trace(chat.conversation_id)
    assert detailed["model_profile"] == "gemma4-remote"
    assert detailed["transport"] == "chat_completions"


def test_health_report_includes_llm_check():
    settings = _settings()
    service = SupportOIDService(settings)
    auth = AuthService(
        users=settings.auth_users,
        session_ttl_seconds=settings.session_ttl_seconds,
        cookie_name=settings.session_cookie_name,
        secure_cookies=False,
        automation_store=None,
        agent_token_ttl_seconds=settings.agent_token_ttl_seconds,
    )
    health = service.get_health_report(auth)
    assert "llm" in health["checks"]
    assert health["checks"]["llm"]["ok"] is False
