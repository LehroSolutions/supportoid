from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.agents.empathy import EmpathyEngine
from src.agents.support_response import SupportResponseEngine
from src.config.settings import Settings


def _settings(tmp_path) -> Settings:
    settings = Settings(
        model_dir=str(tmp_path / "models"),
        kb_dir=str(tmp_path / "knowledge"),
        feedback_dir=str(tmp_path / "feedback"),
        training_dir=str(tmp_path / "training"),
        cost_dir=str(tmp_path / "costs"),
        trace_dir=str(tmp_path / "traces"),
        sqlite_path=str(tmp_path / "app.db"),
        deployment_profile="test",
    )
    for profile in settings.models.values():
        profile["base_url"] = ""
    return settings


def _load_scenarios() -> list[dict]:
    path = Path("tests") / "fixtures" / "ai_eval_scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", _load_scenarios(), ids=lambda item: item["id"])
def test_deterministic_support_scenarios(tmp_path, scenario):
    settings = _settings(tmp_path)
    engine = SupportResponseEngine(settings)
    classification = dict(scenario["classification"])
    empathy = EmpathyEngine().analyze(classification, [])

    result = engine.generate(
        scenario["message"],
        classification,
        empathy,
        list(scenario["kb_results"]),
        conversation_turns=[],
    )

    assert result.source.startswith(scenario["expect_source_prefix"])
    assert result.needs_clarification is scenario["expect_needs_clarification"]
    assert result.should_escalate is scenario["expect_should_escalate"]

    lowered = result.text.lower()
    for phrase in scenario["must_include"]:
        assert phrase.lower() in lowered
    for phrase in scenario["must_not_include"]:
        assert phrase.lower() not in lowered


@pytest.mark.live_llm
def test_live_llm_smoke_is_opt_in(tmp_path):
    if os.getenv("SUPPORTOID_RUN_LIVE_LLM_TESTS", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set SUPPORTOID_RUN_LIVE_LLM_TESTS=1 to enable provider-backed smoke tests.")

    settings = Settings.from_env()
    configured = [
        profile
        for profile in settings.models.values()
        if str(profile.get("base_url", "")).strip()
    ]
    if not configured:
        pytest.skip("No live LLM profiles are configured in the environment.")

    engine = SupportResponseEngine(settings)
    classification = {
        "intent": "account_management",
        "confidence": 0.8,
        "sentiment": -0.1,
        "urgency": 0.2,
        "entities": {},
    }
    empathy = EmpathyEngine().analyze(classification, [])
    result = engine.generate(
        "I need to reset my password.",
        classification,
        empathy,
        [
            {
                "id": "kb-001",
                "title": "Password Reset",
                "content": "Use Forgot Password on the sign-in page and follow the email link.",
                "_score": 10.0,
            }
        ],
        conversation_turns=[],
    )

    assert result.text
    assert "processed your refund" not in result.text.lower()
    assert "ticket has been created" not in result.text.lower()
