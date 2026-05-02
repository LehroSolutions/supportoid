"""
SupportOID Orchestrator
=======================
LLM-first support orchestration with grounded retrieval, safety validation,
human handoff detection, and persistent conversation state.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from src.app.timeutils import utc_now_iso

logger = logging.getLogger("supportoid.orchestrator")


class Orchestrator:
    """Primary support orchestration pipeline."""

    def __init__(self, settings, store=None):
        from src.agents.classifier import IntentClassifier
        from src.agents.empathy import EmpathyEngine
        from src.agents.escalation import EscalationEngine
        from src.agents.feedback import FeedbackAnalyst
        from src.agents.knowledge import KnowledgeRetriever
        from src.agents.quality import QualityAssurance
        from src.agents.support_response import SupportResponseEngine
        from src.app.storage import SQLiteStore

        self.settings = settings
        self.store = store
        if store is not None and hasattr(store, "sqlite"):
            self._conversation_store = store
        else:
            self._conversation_store = SQLiteStore(settings.sqlite_path)

        self.classifier = IntentClassifier(settings)
        self.empathy = EmpathyEngine()
        self.knowledge = KnowledgeRetriever(
            settings.kb_dir,
            seed_dir=getattr(settings, "seed_dir", ""),
            seed_if_empty=bool(getattr(settings, "seed_demo_kb_on_empty", False)),
        )
        self.support_response = SupportResponseEngine(settings)
        self.escalator = EscalationEngine()
        self.quality = QualityAssurance()
        self.feedback = FeedbackAnalyst(settings)

        self.sessions: dict[str, dict[str, Any]] = {}
        self.stats = {
            "total_processed": 0,
            "escalations": 0,
            "avg_confidence": 0.0,
            "avg_quality": 0.0,
            "llm_calls": 0,
            "fallback_events": 0,
            "last_model_profile": "",
            "last_model_family": "",
            "last_transport": "",
        }

    def initialize(self) -> dict:
        stats = self.classifier.get_stats()
        logger.info(
            "Orchestrator ready: %s samples, %s KB entries, acc=%.3f",
            stats.get("training_samples", "?"),
            len(self.knowledge.entries),
            stats.get("accuracy", 0.0),
        )
        return stats

    def process(
        self,
        message: str,
        conversation_id: str = None,
        user_id: str = "anonymous",
    ) -> dict:
        start = time.monotonic()
        conversation_id = conversation_id or f"conv_{uuid.uuid4().hex[:8]}"

        session = self._ensure_session(conversation_id, user_id)
        self._record_turn(
            session,
            role="user",
            content=message,
            metadata={},
        )

        classification = self.classifier.classify(message)
        classification["message"] = message
        session["history"].append(classification)
        self._decorate_last_user_turn(session, classification)

        empathy = self.empathy.analyze(classification, session["messages"][-10:])
        kb_results = self.knowledge.search(
            message,
            classification["intent"],
            classification.get("entities"),
            top_k=3,
        )

        previous_response_id = str(session.get("last_response_id") or "")
        response = self.support_response.generate(
            message,
            classification,
            empathy,
            kb_results,
            conversation_turns=session["messages"][-10:],
            previous_response_id=previous_response_id,
            verified_actions=[],
        )

        quality = self.quality.score(response.text, classification, empathy)
        escalation = self.escalator.evaluate(
            message,
            classification,
            quality.overall,
            session["messages"],
        )
        should_escalate = bool(response.should_escalate or escalation.should_escalate)
        escalation_reason = response.escalation_reason or escalation.reason
        final_response = self._finalize_response_text(
            response.text,
            should_escalate=should_escalate,
            escalation=escalation,
        )

        self._record_turn(
            session,
            role="agent",
            content=final_response,
            metadata={
                "confidence": classification["confidence"],
                "model_profile": response.model_profile,
                "model_family": response.model_family,
                "transport": response.transport,
                "response_id": response.response_id,
                "grounding_ids": response.grounding_ids,
                "source": response.source,
            },
        )
        session["last_response_id"] = response.response_id
        session["last_model_profile"] = response.model_profile
        session["last_model_family"] = response.model_family
        session["last_transport"] = response.transport

        self.feedback.record(
            message,
            classification,
            {"response": final_response, "source": response.source},
            quality.overall,
        )

        total = self.stats["total_processed"] + 1
        self.stats["total_processed"] = total
        self.stats["avg_confidence"] = (
            (self.stats["avg_confidence"] * (total - 1)) + classification["confidence"]
        ) / total
        self.stats["avg_quality"] = (
            (self.stats["avg_quality"] * (total - 1)) + quality.overall
        ) / total
        if should_escalate:
            self.stats["escalations"] += 1
        if response.model_profile:
            self.stats["llm_calls"] += 1
            self.stats["last_model_profile"] = response.model_profile
            self.stats["last_model_family"] = response.model_family
            self.stats["last_transport"] = response.transport
        if response.fallback_used:
            self.stats["fallback_events"] += 1

        return {
            "conversation_id": conversation_id,
            "response": final_response,
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "sentiment": classification["sentiment"],
            "urgency": classification.get("urgency", 0),
            "tone": response.tone or empathy.tone,
            "quality_score": quality.overall,
            "should_escalate": should_escalate,
            "escalation_reason": escalation_reason,
            "source": response.source,
            "kb_results_used": len(kb_results),
            "suggested_actions": response.suggested_actions,
            "processing_time_ms": round((time.monotonic() - start) * 1000, 1),
            "model_name": response.model_name,
            "model_profile": response.model_profile,
            "model_family": response.model_family,
            "transport": response.transport,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_usd": response.cost_usd,
            "response_id": response.response_id,
            "grounding_ids": response.grounding_ids,
            "fallback_used": response.fallback_used,
            "attempts": response.attempts,
        }

    def submit_feedback(
        self,
        conversation_id: str,
        rating: int,
        feedback: str = "",
        corrected_intent: str = "",
    ):
        session = self.sessions.get(conversation_id, {})
        hist = session.get("history", [{}])
        last = hist[-1] if hist else {}
        self.feedback.record(
            last.get("message", ""),
            last,
            {"response": ""},
            user_rating=rating,
            corrected_intent=corrected_intent,
        )
        training_data = self.feedback.get_training_data(
            min_samples=getattr(self.settings, "min_feedback_for_retrain", 10)
        )
        if training_data:
            return self.classifier.retrain(training_data)
        return None

    def get_stats(self) -> dict:
        classifier_stats = self.classifier.get_stats()
        runtime = self.get_runtime_health()
        store_stats = (
            self._conversation_store.stats()
            if hasattr(self._conversation_store, "stats")
            else {}
        )
        return {
            **self.stats,
            "active_sessions": len(self.sessions),
            "model_version": classifier_stats.get("version", 0),
            "model_accuracy": classifier_stats.get("accuracy", 0.0),
            "knowledge_entries": len(self.knowledge.entries),
            "feedback_records": self.feedback.total_count,
            "version": "11.0-llm",
            "configured_model_chain": runtime.get("active_chain", []),
            "model_profiles_configured": runtime.get("configured_profiles", 0),
            "active_model_profile": self.stats.get("last_model_profile", ""),
            "active_model_family": self.stats.get("last_model_family", ""),
            "llm_transport": self.stats.get("last_transport", ""),
            "conversations_persisted": int(store_stats.get("conversations", 0) or 0),
            "conversation_turns_persisted": int(
                store_stats.get("conversation_turns", 0) or 0
            ),
        }

    def get_runtime_health(self) -> Dict[str, Any]:
        status = self.support_response.gateway.runtime_status()
        configured_profiles = 0
        for profile in status.profiles.values():
            if profile.get("configured"):
                configured_profiles += 1
        return {
            "active_chain": status.active_chain,
            "profiles": status.profiles,
            "configured_profiles": configured_profiles,
            "last_model_profile": self.stats.get("last_model_profile", ""),
            "last_model_family": self.stats.get("last_model_family", ""),
            "last_transport": self.stats.get("last_transport", ""),
        }

    def _ensure_session(self, conversation_id: str, user_id: str) -> Dict[str, Any]:
        if conversation_id in self.sessions:
            session = self.sessions[conversation_id]
            session.setdefault("conversation_id", conversation_id)
            if hasattr(self._conversation_store, "save_conversation"):
                self._conversation_store.save_conversation(
                    conversation_id,
                    session.get("user_id", user_id) or user_id,
                    {"created_at": session.get("created_at", utc_now_iso())},
                )
            return session

        persisted_turns = []
        if hasattr(self._conversation_store, "list_conversation_turns"):
            persisted_turns = self._conversation_store.list_conversation_turns(
                conversation_id, limit=100
            )
        if hasattr(self._conversation_store, "save_conversation"):
            self._conversation_store.save_conversation(
                conversation_id,
                user_id,
                {"created_at": utc_now_iso()},
            )
        session = {
            "conversation_id": conversation_id,
            "history": [],
            "messages": [
                {
                    "role": turn.get("role", "user"),
                    "content": turn.get("content", ""),
                    **(turn.get("metadata", {}) or {}),
                }
                for turn in persisted_turns
            ],
            "user_id": user_id,
            "created_at": utc_now_iso(),
            "last_response_id": "",
            "last_model_profile": "",
            "last_model_family": "",
            "last_transport": "",
        }
        if persisted_turns:
            for turn in reversed(persisted_turns):
                metadata = turn.get("metadata", {}) or {}
                if metadata.get("response_id"):
                    session["last_response_id"] = str(metadata.get("response_id"))
                    session["last_model_profile"] = str(
                        metadata.get("model_profile") or ""
                    )
                    session["last_model_family"] = str(
                        metadata.get("model_family") or ""
                    )
                    session["last_transport"] = str(metadata.get("transport") or "")
                    break
        self.sessions[conversation_id] = session
        return session

    def _record_turn(
        self,
        session: Dict[str, Any],
        *,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {"role": role, "content": content}
        payload.update(metadata or {})
        session["messages"].append(payload)
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-100:]
        if hasattr(self._conversation_store, "save_conversation_turn"):
            self._conversation_store.save_conversation_turn(
                self._find_conversation_id_for_session(session),
                role,
                content,
                metadata or {},
            )

    def _decorate_last_user_turn(
        self, session: Dict[str, Any], classification: Dict[str, Any]
    ) -> None:
        for turn in reversed(session["messages"]):
            if turn.get("role") == "user":
                turn["sentiment"] = classification.get("sentiment", 0)
                turn["confidence"] = classification.get("confidence", 0)
                turn["intent"] = classification.get("intent", "general_question")
                break

    @staticmethod
    def _find_conversation_id_for_session(session: Dict[str, Any]) -> str:
        return str(session.get("conversation_id") or "")

    @staticmethod
    def _finalize_response_text(
        text: str,
        *,
        should_escalate: bool,
        escalation,
    ) -> str:
        if not should_escalate:
            return text

        lower = text.lower()
        if "specialist" in lower or "handoff" in lower or "escalat" in lower:
            return text

        handoff_note = (
            f"\n\nThis looks like it should be reviewed by a {escalation.human_role}. "
            "I cannot claim the handoff is already complete, but I do recommend escalating it with the details above."
        )
        return f"{text.rstrip()}{handoff_note}"
