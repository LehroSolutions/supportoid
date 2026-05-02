"""Typed DTO contracts shared by CLI, API, and web layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.app.timeutils import utc_now


class DTOModel(BaseModel):
    """Base DTO model with compatibility helper."""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class LoginRequest(DTOModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class UserContextDTO(DTOModel):
    username: str
    role: Literal["admin", "analyst", "support"]


class LoginResponse(DTOModel):
    ok: bool
    user: Optional[UserContextDTO] = None
    message: str = ""


class ChatRequest(DTOModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = Field(default=None, max_length=120)
    user_id: Optional[str] = Field(default=None, max_length=120)
    tier: str = Field(default="free", max_length=32)


class ChatResponse(DTOModel):
    conversation_id: str
    response: str
    intent: str = "general_question"
    confidence: float = 0.0
    sentiment: float = 0.0
    urgency: float = 0.0
    tone: str = "warm"
    quality_score: float = 0.0
    should_escalate: bool = False
    escalation_reason: str = ""
    source: str = "unknown"
    kb_results_used: int = 0
    suggested_actions: List[str] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    role: Literal["admin", "analyst", "support"] = "support"
    timestamp: datetime = Field(default_factory=utc_now)


class FeedbackRequest(DTOModel):
    conversation_id: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    feedback_text: str = Field(default="", max_length=2000)
    corrected_intent: str = Field(default="", max_length=120)


class FeedbackAck(DTOModel):
    status: Literal["recorded", "rejected"] = "recorded"
    conversation_id: str
    rating: int
    retrain: Optional[Dict[str, Any]] = None
    message: str = ""


class TraceSummary(DTOModel):
    session_id: str
    duration_s: float = 0.0
    steps: int = 0
    error: Optional[str] = None
    user_input: str = ""
    summary: str = ""
    escalated: bool = False


class CostSummary(DTOModel):
    conversation_id: Optional[str] = None
    total_conversations: int = 0
    total_cost_usd: float = 0.0
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cost_by_model: Dict[str, float] = Field(default_factory=dict)
    calls_by_model: Dict[str, int] = Field(default_factory=dict)


class KBQualityReport(DTOModel):
    total_entries: int = 0
    overall_avg: float = 0.0
    grade_distribution: Dict[str, int] = Field(default_factory=dict)
    dimension_averages: Dict[str, float] = Field(default_factory=dict)
    top_entries: Dict[str, Any] = Field(default_factory=dict)
    needs_attention: Dict[str, Any] = Field(default_factory=dict)
    report_generated: Optional[str] = None


class StatsReport(DTOModel):
    version: str = "v1"
    total_processed: int = 0
    escalations: int = 0
    avg_confidence: float = 0.0
    avg_quality: float = 0.0
    active_sessions: int = 0
    model_version: int = 0
    model_accuracy: float = 0.0
    knowledge_entries: int = 0
    feedback_records: int = 0
    cache_hit_rate: float = 0.0
    errors: int = 0
    traces: int = 0
    costs: CostSummary = Field(default_factory=CostSummary)
    active_model_profile: str = ""
    active_model_family: str = ""
    llm_transport: str = ""
    configured_model_chain: List[str] = Field(default_factory=list)
    fallback_events: int = 0


class ProblemDetail(DTOModel):
    type: str = "about:blank"
    title: str = "Error"
    status: int = 500
    detail: str = ""
    instance: Optional[str] = None
    request_id: Optional[str] = None


class PaginationResponse(DTOModel):
    items: List[Any] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False
