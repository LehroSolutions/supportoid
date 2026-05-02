"""Stabilized core gate tests for upgraded SupportOID runtime."""

from __future__ import annotations

import uuid
from pathlib import Path

from src.app.dto import ChatRequest, FeedbackRequest
from src.app.service import SupportOIDService
from src.config.settings import Settings


def _isolated_settings() -> Settings:
    root = Path("data") / "test_tmp" / f"core_{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return Settings(
        model_dir=str(root / "models"),
        kb_dir=str(root / "knowledge"),
        feedback_dir=str(root / "feedback"),
        training_dir=str(root / "training"),
        cost_dir=str(root / "costs"),
        trace_dir=str(root / "traces"),
        sqlite_path=str(root / "app.db"),
        convex_adapter_url="",
        deployment_profile="test",
        seed_demo_kb_on_empty=True,
    )


def test_core_chat_feedback_trace_stats():
    settings = _isolated_settings()
    service = SupportOIDService(settings)

    chat = service.chat(ChatRequest(message="How do I reset my password?"), actor="support")
    assert chat.conversation_id
    assert chat.response
    assert chat.processing_time_ms >= 0

    ack = service.record_feedback(
        FeedbackRequest(
            conversation_id=chat.conversation_id,
            rating=4,
            feedback_text="Helpful answer",
        )
    )
    assert ack.status == "recorded"

    traces = service.list_trace_summaries(limit=10)
    assert len(traces) >= 1
    assert traces[0].session_id

    stats = service.get_stats_report()
    assert stats.traces >= 1
    assert stats.total_processed >= 0


def test_core_migration_and_sync_paths():
    settings = _isolated_settings()
    service = SupportOIDService(settings)

    # Pre-seed one trace and one feedback then force a sync run.
    service.chat(ChatRequest(message="Billing question"), actor="support")
    result = service.run_sync(limit=50)
    assert "attempted" in result
    assert "synced" in result
    assert "failed" in result
