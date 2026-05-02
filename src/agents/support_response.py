"""LLM-first support response engine with grounding and safety validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.agents.llm_gateway import GatewayAttempt, LLMGateway


UNSUPPORTED_ACTION_PATTERNS = [
    re.compile(
        r"\b(i(?:'ve| have)?\s+(?:already\s+)?(?:issued|processed|initiated|completed|submitted|created|escalated|scheduled|waived|applied))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:we|our team)\s+(?:have|has)\s+(?:already\s+)?(?:issued|processed|created|escalated|scheduled|submitted)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:your|the)\s+(?:refund|credit|ticket|case|callback|escalation)\s+has\s+been\s+(?:issued|processed|created|scheduled|submitted|completed)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bi(?:'m| am)\s+connecting\s+you\s+(?:right now|now)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:a|the)\s+(?:ticket|case|callback)\s+(?:is|was)\s+(?:already\s+)?(?:created|scheduled|submitted)\b",
        re.IGNORECASE,
    ),
]


SUPPORT_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"},
        "tone": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
        "should_escalate": {"type": "boolean"},
        "escalation_reason": {"type": "string"},
        "suggested_actions": {"type": "array", "items": {"type": "string"}},
        "grounding_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "answer",
        "confidence",
        "tone",
        "needs_clarification",
        "should_escalate",
        "escalation_reason",
        "suggested_actions",
        "grounding_ids",
    ],
    "additionalProperties": False,
}


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    normalized_grounding_ids: List[str] = field(default_factory=list)


@dataclass
class SupportResponseResult:
    text: str
    source: str
    suggested_actions: List[str]
    model_name: str = ""
    model_profile: str = ""
    model_family: str = ""
    transport: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    response_id: str = ""
    confidence: float = 0.0
    tone: str = "warm"
    needs_clarification: bool = False
    should_escalate: bool = False
    escalation_reason: str = ""
    grounding_ids: List[str] = field(default_factory=list)
    fallback_used: bool = False
    attempts: List[Dict[str, Any]] = field(default_factory=list)


class ResponseValidator:
    """Rejects unsupported promises or malformed structured payloads."""

    def validate(
        self,
        payload: Dict[str, Any],
        *,
        kb_results: List[Dict[str, Any]],
        classification: Dict[str, Any],
        verified_actions: Optional[List[str]] = None,
    ) -> ValidationResult:
        answer = str(payload.get("answer") or "").strip()
        if len(answer) < 20:
            return ValidationResult(ok=False, reason="answer_too_short")

        for pattern in UNSUPPORTED_ACTION_PATTERNS:
            if pattern.search(answer):
                if not verified_actions:
                    return ValidationResult(ok=False, reason="unsupported_action_claim")

        allowed_grounding_ids = {
            str(item.get("id"))
            for item in kb_results
            if isinstance(item, dict) and item.get("id")
        }
        normalized_grounding_ids = []
        for raw_id in payload.get("grounding_ids") or []:
            raw_id = str(raw_id)
            if raw_id in allowed_grounding_ids:
                normalized_grounding_ids.append(raw_id)

        needs_clarification = bool(payload.get("needs_clarification", False))
        try:
            confidence = float(payload.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if kb_results and not normalized_grounding_ids and not needs_clarification:
            return ValidationResult(ok=False, reason="grounding_required")

        if not kb_results and confidence >= 0.8 and not needs_clarification:
            return ValidationResult(ok=False, reason="ungrounded_high_confidence")

        intent = str(classification.get("intent") or "")
        sentiment = float(classification.get("sentiment", 0.0) or 0.0)
        should_escalate = bool(payload.get("should_escalate", False))
        if intent in {"complaint", "escalation"} and sentiment <= -0.6 and not should_escalate:
            return ValidationResult(ok=False, reason="escalation_required")

        return ValidationResult(
            ok=True,
            normalized_grounding_ids=normalized_grounding_ids,
        )


class SupportResponseEngine:
    """Build grounded prompts, validate outputs, and fall back safely."""

    def __init__(self, settings, gateway: Optional[LLMGateway] = None):
        self.settings = settings
        self.gateway = gateway or LLMGateway(settings)
        self.validator = ResponseValidator()

    def generate(
        self,
        message: str,
        classification: Dict[str, Any],
        empathy,
        kb_results: List[Dict[str, Any]],
        conversation_turns: Optional[List[Dict[str, Any]]] = None,
        previous_response_id: str = "",
        verified_actions: Optional[List[str]] = None,
    ) -> SupportResponseResult:
        context_bundle = self._build_context_bundle(
            message,
            classification,
            empathy,
            kb_results,
            conversation_turns or [],
        )
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context_bundle)

        attempts: List[Dict[str, Any]] = []
        for profile in self.gateway.ordered_profiles():
            attempt = self.gateway.invoke_profile(
                profile,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=SUPPORT_RESPONSE_SCHEMA,
                previous_response_id=previous_response_id,
            )
            attempts.append(attempt.to_trace())
            if not attempt.ok or attempt.payload is None:
                continue

            normalized = self._normalize_payload(
                attempt.payload,
                classification=classification,
                empathy=empathy,
            )
            validation = self.validator.validate(
                normalized,
                kb_results=kb_results,
                classification=classification,
                verified_actions=verified_actions,
            )
            if not validation.ok:
                attempts[-1]["validation_error"] = validation.reason
                continue

            return SupportResponseResult(
                text=normalized["answer"],
                source=f"llm:{profile.name}",
                suggested_actions=normalized["suggested_actions"],
                model_name=profile.name,
                model_profile=profile.name,
                model_family=profile.family,
                transport=profile.transport,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                response_id=attempt.response_id,
                confidence=normalized["confidence"],
                tone=normalized["tone"],
                needs_clarification=normalized["needs_clarification"],
                should_escalate=normalized["should_escalate"],
                escalation_reason=normalized["escalation_reason"],
                grounding_ids=validation.normalized_grounding_ids,
                fallback_used=len(attempts) > 1,
                attempts=attempts,
            )

        fallback = self._safe_fallback(
            message,
            classification=classification,
            empathy=empathy,
            kb_results=kb_results,
        )
        fallback.attempts = attempts
        fallback.fallback_used = True
        return fallback

    @staticmethod
    def _build_system_prompt() -> str:
        return (
            "You are the support response engine for SupportOID. "
            "Produce calm, accurate, grounded customer-support responses. "
            "Use only the facts provided in the conversation context and knowledge base excerpts. "
            "Do not claim that you issued refunds, created tickets, escalated cases, scheduled callbacks, "
            "or completed any backend action unless the context explicitly says a verified action exists. "
            "If evidence is weak or missing, ask a concise clarifying question. "
            "If the issue is legal, security-sensitive, financial-dispute related, or the user explicitly wants a human, "
            "recommend safe handoff without pretending the handoff is already done. "
            "Return only a JSON object matching the requested schema."
        )

    def _build_context_bundle(
        self,
        message: str,
        classification: Dict[str, Any],
        empathy,
        kb_results: List[Dict[str, Any]],
        conversation_turns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        turns = []
        for turn in conversation_turns[-6:]:
            turns.append(
                {
                    "role": turn.get("role", "user"),
                    "content": str(turn.get("content") or "")[:500],
                }
            )

        kb_context = []
        for item in kb_results[:3]:
            kb_context.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "content": str(item.get("content") or "")[:1000],
                    "score": round(float(item.get("_score", 0.0) or 0.0), 3),
                }
            )

        return {
            "message": message,
            "intent": classification.get("intent", "general_question"),
            "confidence": classification.get("confidence", 0.0),
            "sentiment": classification.get("sentiment", 0.0),
            "urgency": classification.get("urgency", 0.0),
            "entities": classification.get("entities", {}),
            "tone": getattr(empathy, "tone", "warm"),
            "strategy": getattr(empathy, "strategy", "solve"),
            "conversation": turns,
            "kb": kb_context,
            "policy": {
                "verified_actions": [],
                "safe_handoff": True,
            },
        }

    def _build_user_prompt(self, context_bundle: Dict[str, Any]) -> str:
        return (
            "Support request context:\n"
            f"{context_bundle}\n\n"
            "Write the best possible answer for the customer. "
            "The answer should be actionable, empathetic, and concise. "
            "Prefer grounded knowledge-base facts when available."
        )

    @staticmethod
    def _normalize_payload(
        payload: Dict[str, Any],
        *,
        classification: Dict[str, Any],
        empathy,
    ) -> Dict[str, Any]:
        answer = str(payload.get("answer") or "").strip()
        answer = answer.replace("\r\n", "\n").strip()
        confidence = payload.get("confidence", classification.get("confidence", 0.0))
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = float(classification.get("confidence", 0.0) or 0.0)

        suggested_actions = [
            str(item).strip()
            for item in (payload.get("suggested_actions") or [])
            if str(item).strip()
        ][:4]
        if not suggested_actions:
            suggested_actions = ["Ask follow-up question"]

        return {
            "answer": answer,
            "confidence": max(0.0, min(1.0, confidence)),
            "tone": str(payload.get("tone") or getattr(empathy, "tone", "warm")),
            "needs_clarification": bool(payload.get("needs_clarification", False)),
            "should_escalate": bool(payload.get("should_escalate", False)),
            "escalation_reason": str(payload.get("escalation_reason") or ""),
            "suggested_actions": suggested_actions,
            "grounding_ids": [
                str(item).strip()
                for item in (payload.get("grounding_ids") or [])
                if str(item).strip()
            ],
        }

    def _safe_fallback(
        self,
        message: str,
        *,
        classification: Dict[str, Any],
        empathy,
        kb_results: List[Dict[str, Any]],
    ) -> SupportResponseResult:
        intent = str(classification.get("intent") or "general_question")
        greeting = getattr(empathy, "greeting", "I can help with that.")
        closing = getattr(empathy, "closing", "Let me know what you want to do next.")

        if kb_results:
            best = kb_results[0]
            best_score = float(best.get("_score", 0.0) or 0.0)
            if best_score < 1.0:
                return SupportResponseResult(
                    text=(
                        f"{greeting}\n\n"
                        "I found a possible match, but the details are not strong enough for me to answer confidently yet. "
                        f"{self._follow_up(intent)}\n\n"
                        f"{closing}"
                    ),
                    source="fallback:clarify-weak-grounding",
                    suggested_actions=self._default_actions(intent),
                    confidence=max(0.3, float(classification.get("confidence", 0.0) or 0.0)),
                    tone=getattr(empathy, "tone", "warm"),
                    needs_clarification=True,
                    should_escalate=False,
                    grounding_ids=[],
                )
            title = str(best.get("title") or "our support notes")
            content = str(best.get("content") or "").strip()
            answer = (
                f"{greeting}\n\n"
                f"Based on {title}, here is the most relevant guidance:\n\n"
                f"{content}\n\n"
                f"{self._follow_up(intent)}\n\n"
                f"{closing}"
            )
            return SupportResponseResult(
                text=answer,
                source="fallback:grounded-kb",
                suggested_actions=self._default_actions(intent),
                confidence=max(0.45, float(classification.get("confidence", 0.0) or 0.0)),
                tone=getattr(empathy, "tone", "warm"),
                needs_clarification=False,
                should_escalate=False,
                grounding_ids=[str(best.get("id"))] if best.get("id") else [],
            )

        if intent == "technical_issue":
            answer = (
                f"{greeting}\n\n"
                "I want to narrow this down carefully. Please reply with:\n"
                "1. What you were trying to do\n"
                "2. Any error text you saw\n"
                "3. Your browser or device\n\n"
                "If the issue is blocking work right now, say that and I will recommend a fast handoff path.\n\n"
                f"{closing}"
            )
        elif intent == "refund_request":
            answer = (
                f"{greeting}\n\n"
                "I can help you prepare a refund review. I cannot confirm a refund from this channel, "
                "but I can help you collect the key details: the plan name, charge date, amount, and the reason for the request.\n\n"
                "Reply with those details and I will summarize the case clearly for the next step.\n\n"
                f"{closing}"
            )
        elif intent in {"complaint", "escalation"}:
            answer = (
                f"{greeting}\n\n"
                "I hear the frustration here. This looks like a case that should be reviewed by a specialist. "
                "I cannot claim the handoff is already completed, but I can help package the issue clearly and recommend escalation.\n\n"
                "Tell me the impact, how long this has been happening, and any case or billing reference you already have.\n\n"
                f"{closing}"
            )
        else:
            answer = (
                f"{greeting}\n\n"
                f"I want to make sure I answer this accurately. From your message, I understand the topic is: \"{message[:160]}\".\n\n"
                "If you can share one or two more specifics, I can give a much more precise next step.\n\n"
                f"{closing}"
            )

        should_escalate = intent in {"complaint", "escalation"}
        return SupportResponseResult(
            text=answer,
            source="fallback:heuristic-safe",
            suggested_actions=self._default_actions(intent),
            confidence=max(0.35, float(classification.get("confidence", 0.0) or 0.0)),
            tone=getattr(empathy, "tone", "warm"),
            needs_clarification=True,
            should_escalate=should_escalate,
            escalation_reason="safe_handoff_recommended" if should_escalate else "",
            grounding_ids=[],
        )

    @staticmethod
    def _follow_up(intent: str) -> str:
        if intent == "technical_issue":
            return "If you can share the exact error text or a screenshot, I can narrow this down further."
        if intent == "product_inquiry":
            return "If you want, I can compare the options side by side."
        if intent == "billing_inquiry":
            return "If you share the plan or invoice context, I can make this more specific."
        return "If you want, I can help with the next step from here."

    @staticmethod
    def _default_actions(intent: str) -> List[str]:
        actions = {
            "technical_issue": ["Collect error details", "Recommend specialist handoff"],
            "refund_request": ["Collect refund details", "Review policy"],
            "complaint": ["Prepare escalation summary", "Collect impact details"],
            "billing_inquiry": ["Review billing details", "Collect invoice context"],
        }
        return actions.get(intent, ["Ask follow-up question"])
