"""DTOs for agent-facing automation APIs and CLI."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.app.dto import ChatRequest, FeedbackRequest, ProblemDetail
from src.app.timeutils import utc_now_iso


class EmptyInput(BaseModel):
    pass


class TraceListInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class TraceGetInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=120)


class CostsGetInput(BaseModel):
    conversation_id: Optional[str] = Field(default=None, max_length=120)


class SyncRunInput(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=500)


class ServiceAccountCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    role: Literal["admin", "analyst", "support"] = "support"
    scopes: List[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=500)
    expires_in_seconds: Optional[int] = Field(default=None, ge=60, le=31_536_000)


class ServiceAccountView(BaseModel):
    account_id: str
    name: str
    role: Literal["admin", "analyst", "support"]
    scopes: List[str] = Field(default_factory=list)
    description: str = ""
    created_at: str
    updated_at: str
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ServiceAccountSecret(ServiceAccountView):
    token: str


class CapabilityItem(BaseModel):
    operation_id: str
    title: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_scopes: List[str] = Field(default_factory=list)
    mutation_level: Literal["read", "safe_write", "approval_required"]
    approval_required: bool = False
    idempotent: bool = False
    execution_mode: Literal["sync", "job"]


class CapabilityListResult(BaseModel):
    items: List[CapabilityItem]


class InvokeRequest(BaseModel):
    operation_id: str = Field(min_length=1, max_length=120)
    input: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
    approval_mode: Optional[str] = Field(default=None, max_length=40)


class JobRecordView(BaseModel):
    job_id: str
    operation_id: str
    status: str
    request_id: str
    approval_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


class JobListResult(BaseModel):
    items: List[JobRecordView]


class ApprovalRecordView(BaseModel):
    approval_id: str
    operation_id: str
    status: str
    request_id: str
    job_id: Optional[str] = None
    decision_reason: str = ""
    created_at: str
    updated_at: str
    decided_at: Optional[str] = None


class ApprovalResult(BaseModel):
    approval: ApprovalRecordView


class ServiceAccountListResult(BaseModel):
    items: List[ServiceAccountView]


class AutomationEnvelope(BaseModel):
    ok: bool
    status: str
    operation_id: str
    request_id: str
    job_id: Optional[str] = None
    approval_id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[ProblemDetail] = None
    timestamp: str = Field(default_factory=utc_now_iso)
    next_action: Optional[str] = None


class CacheClearResult(BaseModel):
    cleared: int = 0


class MemoryCleanupResult(BaseModel):
    freed_mb: float = 0.0


class SyncOperationResult(BaseModel):
    attempted: int = 0
    synced: int = 0
    failed: int = 0
    errors: List[str] = Field(default_factory=list)


class FeedbackOperationInput(FeedbackRequest):
    pass


class ChatOperationInput(ChatRequest):
    pass
