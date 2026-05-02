"""Canonical automation registry and executor for agent-facing API and CLI use."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Dict, Iterable, Optional, Type

from pydantic import BaseModel, ValidationError

from src.app.auth import (
    AutomationPrincipal,
    AuthService,
    normalize_service_account_scopes,
)
from src.app.automation_dto import (
    ApprovalDecisionRequest,
    ApprovalRecordView,
    ApprovalResult,
    AutomationEnvelope,
    CacheClearResult,
    CapabilityItem,
    CapabilityListResult,
    ChatOperationInput,
    CostsGetInput,
    EmptyInput,
    FeedbackOperationInput,
    JobListResult,
    JobRecordView,
    MemoryCleanupResult,
    ServiceAccountCreateRequest,
    ServiceAccountListResult,
    ServiceAccountSecret,
    ServiceAccountView,
    SyncOperationResult,
    SyncRunInput,
    TraceGetInput,
    TraceListInput,
)
from src.app.automation_store import AutomationStore
from src.app.dto import (
    ChatResponse,
    CostSummary,
    FeedbackAck,
    KBQualityReport,
    PaginationResponse,
    ProblemDetail,
    StatsReport,
)
from src.app.service import SupportOIDService
from src.app.timeutils import utc_now_iso


class AutomationProblem(Exception):
    """Structured problem for agent invocation failures."""

    def __init__(self, status_code: int, title: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail


@dataclass(frozen=True)
class AutomationOperation:
    operation_id: str
    title: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel] | None
    output_schema: Dict[str, Any] | None
    allowed_roles: tuple[str, ...]
    required_scopes: tuple[str, ...]
    mutation_level: str
    approval_required: bool
    idempotent: bool
    execution_mode: str
    handler: Callable[[BaseModel, AutomationPrincipal], Any]


def _problem(
    status_code: int, title: str, detail: str, request_id: str
) -> ProblemDetail:
    return ProblemDetail(
        type=f"https://supportoid.dev/errors/{status_code}",
        title=title,
        status=status_code,
        detail=detail,
        request_id=request_id,
    )


def _iso_or_none(value: float | None) -> str | None:
    if value is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _model_schema(model: Type[BaseModel] | None, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if model is not None:
        return model.model_json_schema()
    return fallback or {"type": "object"}


def _args_hash(
    principal: AutomationPrincipal, operation_id: str, input_payload: Dict[str, Any]
) -> str:
    return sha256(
        json.dumps(
            {
                "operation_id": operation_id,
                "principal_id": principal.principal_id,
                "input": input_payload,
            },
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


class AutomationService:
    """Shared automation execution surface for API and CLI."""

    def __init__(
        self,
        service: SupportOIDService,
        auth: AuthService,
        store: AutomationStore,
        start_time_provider: Callable[[], float] | None = None,
    ):
        self.service = service
        self.auth = auth
        self.store = store
        self.start_time_provider = start_time_provider or (lambda: 0.0)
        self._operations = self._build_registry()

    @property
    def operations(self) -> Dict[str, AutomationOperation]:
        return self._operations

    def _build_registry(self) -> Dict[str, AutomationOperation]:
        operations = [
            AutomationOperation(
                operation_id="chat.send",
                title="Send Chat Message",
                description="Submit a support chat request through the orchestration pipeline.",
                input_model=ChatOperationInput,
                output_model=ChatResponse,
                output_schema=None,
                allowed_roles=("admin", "analyst", "support"),
                required_scopes=("chat:write",),
                mutation_level="safe_write",
                approval_required=False,
                idempotent=True,
                execution_mode="sync",
                handler=lambda payload, principal: self.service.chat(
                    payload,
                    actor=principal.display_name,
                ).model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="feedback.record",
                title="Record Feedback",
                description="Record user feedback against a conversation.",
                input_model=FeedbackOperationInput,
                output_model=FeedbackAck,
                output_schema=None,
                allowed_roles=("admin", "analyst", "support"),
                required_scopes=("feedback:write",),
                mutation_level="safe_write",
                approval_required=False,
                idempotent=True,
                execution_mode="sync",
                handler=lambda payload, _principal: self.service.record_feedback(
                    payload
                ).model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="traces.list",
                title="List Traces",
                description="List paginated conversation traces.",
                input_model=TraceListInput,
                output_model=PaginationResponse,
                output_schema=None,
                allowed_roles=("admin", "analyst", "support"),
                required_scopes=("traces:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda payload, _principal: self.service.list_trace_page(
                    limit=payload.limit,
                    offset=payload.offset,
                ).model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="trace.get",
                title="Get Trace",
                description="Fetch a single trace by session ID.",
                input_model=TraceGetInput,
                output_model=None,
                output_schema={"type": "object"},
                allowed_roles=("admin", "analyst", "support"),
                required_scopes=("trace:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda payload, _principal: self._require_trace(payload.session_id),
            ),
            AutomationOperation(
                operation_id="stats.get",
                title="Get Stats",
                description="Fetch aggregate analytics and platform stats.",
                input_model=EmptyInput,
                output_model=StatsReport,
                output_schema=None,
                allowed_roles=("admin", "analyst"),
                required_scopes=("stats:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda _payload, _principal: self.service.get_stats_report().model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="costs.get",
                title="Get Costs",
                description="Fetch usage cost summaries for the platform or a conversation.",
                input_model=CostsGetInput,
                output_model=CostSummary,
                output_schema=None,
                allowed_roles=("admin", "analyst"),
                required_scopes=("costs:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda payload, _principal: self.service.get_cost_summary(
                    conversation_id=payload.conversation_id
                ).model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="kb.quality.get",
                title="Get KB Quality",
                description="Fetch knowledge-base quality metrics.",
                input_model=EmptyInput,
                output_model=KBQualityReport,
                output_schema=None,
                allowed_roles=("admin", "analyst"),
                required_scopes=("kb:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda _payload, _principal: self.service.get_kb_quality_report().model_dump(mode="json"),
            ),
            AutomationOperation(
                operation_id="health.get",
                title="Get Health",
                description="Fetch the public health report.",
                input_model=EmptyInput,
                output_model=None,
                output_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                        "uptime_seconds": {"type": "number"},
                        "checks": {"type": "object"},
                    },
                },
                allowed_roles=("admin", "analyst", "support"),
                required_scopes=("health:read",),
                mutation_level="read",
                approval_required=False,
                idempotent=False,
                execution_mode="sync",
                handler=lambda _payload, _principal: self.service.get_health_report(
                    self.auth,
                    start_time=self.start_time_provider(),
                ),
            ),
            AutomationOperation(
                operation_id="sync.run",
                title="Run Sync",
                description="Flush queued adapter sync events.",
                input_model=SyncRunInput,
                output_model=SyncOperationResult,
                output_schema=None,
                allowed_roles=("admin",),
                required_scopes=("sync:run",),
                mutation_level="approval_required",
                approval_required=True,
                idempotent=True,
                execution_mode="job",
                handler=lambda payload, _principal: self.service.run_sync(limit=payload.limit),
            ),
            AutomationOperation(
                operation_id="migrate.run",
                title="Run Migration",
                description="Import legacy JSON and trigger a sync pass.",
                input_model=EmptyInput,
                output_model=None,
                output_schema={"type": "object"},
                allowed_roles=("admin",),
                required_scopes=("migrate:run",),
                mutation_level="approval_required",
                approval_required=True,
                idempotent=True,
                execution_mode="job",
                handler=lambda _payload, _principal: self.service.migrate_legacy_data(),
            ),
            AutomationOperation(
                operation_id="admin.cache.clear",
                title="Clear Cache",
                description="Clear cached orchestration responses.",
                input_model=EmptyInput,
                output_model=CacheClearResult,
                output_schema=None,
                allowed_roles=("admin",),
                required_scopes=("cache:clear",),
                mutation_level="approval_required",
                approval_required=True,
                idempotent=True,
                execution_mode="job",
                handler=lambda _payload, _principal: self.service.clear_cache(),
            ),
            AutomationOperation(
                operation_id="admin.memory.cleanup",
                title="Cleanup Memory",
                description="Run memory cleanup routines.",
                input_model=EmptyInput,
                output_model=MemoryCleanupResult,
                output_schema=None,
                allowed_roles=("admin",),
                required_scopes=("memory:cleanup",),
                mutation_level="approval_required",
                approval_required=True,
                idempotent=True,
                execution_mode="job",
                handler=lambda _payload, _principal: self.service.cleanup_memory(),
            ),
        ]
        return {operation.operation_id: operation for operation in operations}

    def _require_trace(self, session_id: str) -> Dict[str, Any]:
        trace = self.service.get_trace(session_id)
        if not trace:
            raise AutomationProblem(404, "Trace not found", "Trace not found")
        return trace

    def _principal_can_access(
        self, principal: AutomationPrincipal, operation: AutomationOperation
    ) -> bool:
        if principal.role not in operation.allowed_roles and principal.role != "admin":
            return False
        return principal.has_scopes(operation.required_scopes)

    def _require_access(
        self, principal: AutomationPrincipal, operation: AutomationOperation
    ) -> None:
        if principal.role not in operation.allowed_roles and principal.role != "admin":
            raise AutomationProblem(
                403,
                "Role cannot access operation",
                "Role cannot access this operation",
            )
        if not principal.has_scopes(operation.required_scopes):
            raise AutomationProblem(
                403,
                "Scope cannot access operation",
                "Required capability scope is missing",
            )

    def _serialize_job_record(self, record: Dict[str, Any]) -> JobRecordView:
        return JobRecordView(
            job_id=record["job_id"],
            operation_id=record["operation_id"],
            status=record["status"],
            request_id=record["request_id"],
            approval_id=record.get("approval_id"),
            result=record.get("result"),
            error=record.get("error"),
            created_at=_iso_or_none(record.get("created_at")) or utc_now_iso(),
            updated_at=_iso_or_none(record.get("updated_at")) or utc_now_iso(),
        )

    def _serialize_approval_record(self, record: Dict[str, Any]) -> ApprovalRecordView:
        return ApprovalRecordView(
            approval_id=record["approval_id"],
            operation_id=record["operation_id"],
            status=record["status"],
            request_id=record["request_id"],
            job_id=record.get("job_id"),
            decision_reason=record.get("decision_reason") or "",
            created_at=_iso_or_none(record.get("created_at")) or utc_now_iso(),
            updated_at=_iso_or_none(record.get("updated_at")) or utc_now_iso(),
            decided_at=_iso_or_none(record.get("decided_at")),
        )

    def serialize_service_account(self, record: Dict[str, Any]) -> ServiceAccountView:
        return ServiceAccountView(
            account_id=record["account_id"],
            name=record["name"],
            role=record["role"],
            scopes=list(record.get("scopes", [])),
            description=record.get("description", ""),
            created_at=_iso_or_none(record.get("created_at")) or utc_now_iso(),
            updated_at=_iso_or_none(record.get("updated_at")) or utc_now_iso(),
            expires_at=_iso_or_none(record.get("expires_at")),
            revoked_at=_iso_or_none(record.get("revoked_at")),
        )

    def _envelope(
        self,
        *,
        ok: bool,
        status: str,
        operation_id: str,
        request_id: str,
        job_id: str | None = None,
        approval_id: str | None = None,
        result: Any = None,
        error: ProblemDetail | None = None,
        next_action: str | None = None,
    ) -> AutomationEnvelope:
        return AutomationEnvelope(
            ok=ok,
            status=status,
            operation_id=operation_id,
            request_id=request_id,
            job_id=job_id,
            approval_id=approval_id,
            result=result,
            error=error,
            next_action=next_action,
        )

    def _audit(
        self,
        *,
        principal: AutomationPrincipal,
        operation_id: str,
        request_id: str,
        idempotency_key: str | None,
        input_payload: Dict[str, Any],
        envelope: AutomationEnvelope,
        approval_state: str | None,
    ) -> None:
        self.store.record_audit_event(
            audit_id=f"audit_{uuid.uuid4().hex[:16]}",
            principal_type=principal.principal_type,
            principal_id=principal.principal_id,
            operation_id=operation_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            args_hash=_args_hash(principal, operation_id, input_payload),
            outcome_status=envelope.status,
            approval_state=approval_state,
            envelope=envelope.model_dump(mode="json"),
        )

    def _require_management_scope(
        self, principal: AutomationPrincipal, scope: str
    ) -> None:
        if principal.role == "admin" or principal.has_scopes([scope]):
            return
        raise AutomationProblem(
            403,
            "Scope cannot access management operation",
            f"{scope} scope required",
        )

    def _rehydrate_principal(self, approval: Dict[str, Any]) -> AutomationPrincipal:
        if approval["principal_type"] == "local":
            return AutomationPrincipal(
                principal_id="local-system",
                principal_type="local",
                display_name="local-system",
                role="admin",
                scopes=["*"],
            )

        accounts = self.auth.list_service_accounts(include_revoked=True)
        for account in accounts:
            if account["account_id"] == approval["principal_id"]:
                return AutomationPrincipal(
                    principal_id=account["account_id"],
                    principal_type="service_account",
                    display_name=account["name"],
                    role=account["role"],
                    scopes=list(account.get("scopes", [])),
                )

        raise AutomationProblem(
            404,
            "Principal not found",
            "The original service account no longer exists",
        )

    def list_capabilities(
        self, principal: AutomationPrincipal, request_id: str
    ) -> AutomationEnvelope:
        items = [
            CapabilityItem(
                operation_id=operation.operation_id,
                title=operation.title,
                description=operation.description,
                input_schema=_model_schema(operation.input_model),
                output_schema=_model_schema(
                    operation.output_model, operation.output_schema
                ),
                required_scopes=list(operation.required_scopes),
                mutation_level=operation.mutation_level,  # type: ignore[arg-type]
                approval_required=operation.approval_required,
                idempotent=operation.idempotent,
                execution_mode=operation.execution_mode,  # type: ignore[arg-type]
            )
            for operation in self._operations.values()
            if self._principal_can_access(principal, operation)
        ]
        return self._envelope(
            ok=True,
            status="completed",
            operation_id="agent.capabilities",
            request_id=request_id,
            result=CapabilityListResult(items=items).model_dump(mode="json"),
        )

    def invoke(
        self,
        principal: AutomationPrincipal,
        operation_id: str,
        input_payload: Dict[str, Any] | None = None,
        *,
        request_id: str,
        idempotency_key: str | None = None,
        approval_mode: str | None = None,
    ) -> AutomationEnvelope:
        payload = dict(input_payload or {})
        operation = self._operations.get(operation_id)
        if not operation:
            raise AutomationProblem(404, "Operation not found", "Operation not found")
        self._require_access(principal, operation)

        if operation.idempotent and operation.mutation_level != "read" and not idempotency_key:
            raise AutomationProblem(
                400,
                "Idempotency key required",
                "Idempotency-Key is required for mutating agent operations",
            )

        try:
            typed_payload = operation.input_model.model_validate(payload)
        except ValidationError as exc:
            raise AutomationProblem(422, "Validation failed", str(exc)) from exc

        normalized_payload = typed_payload.model_dump(mode="json")

        if idempotency_key:
            previous = self.store.find_idempotent_record(
                principal_type=principal.principal_type,
                principal_id=principal.principal_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
            )
            if previous is not None:
                if previous["args_hash"] != _args_hash(
                    principal,
                    operation_id,
                    normalized_payload,
                ):
                    raise AutomationProblem(
                        409,
                        "Idempotency conflict",
                        "Idempotency-Key has already been used with different input",
                    )
                return AutomationEnvelope.model_validate(previous["envelope"])

        if operation.approval_required:
            approval_id = f"approval_{uuid.uuid4().hex[:12]}"
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            approval_record = self.store.create_approval(
                approval_id=approval_id,
                operation_id=operation_id,
                principal_type=principal.principal_type,
                principal_id=principal.principal_id,
                request_id=request_id,
                input_payload=typed_payload.model_dump(mode="json"),
            )
            self.store.create_job(
                job_id=job_id,
                operation_id=operation_id,
                principal_type=principal.principal_type,
                principal_id=principal.principal_id,
                status="waiting_approval",
                request_id=request_id,
                input_payload=typed_payload.model_dump(mode="json"),
                idempotency_key=idempotency_key,
                approval_id=approval_id,
            )
            self.store.update_approval(
                approval_id=approval_id,
                status=approval_record["status"],
                decision_reason=approval_record.get("decision_reason", ""),
                decided_by=approval_record.get("decided_by", ""),
                job_id=job_id,
            )
            envelope = self._envelope(
                ok=True,
                status="approval_required",
                operation_id=operation_id,
                request_id=request_id,
                job_id=job_id,
                approval_id=approval_id,
                next_action=f"approve:{approval_id}",
                result={
                    "approval_mode": approval_mode or "manual",
                    "message": "Operation requires approval before execution",
                },
            )
            self._audit(
                principal=principal,
                operation_id=operation_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                input_payload=normalized_payload,
                envelope=envelope,
                approval_state="pending",
            )
            return envelope

        try:
            result = operation.handler(typed_payload, principal)
        except AutomationProblem:
            raise
        except Exception as exc:  # pragma: no cover - safety net
            raise AutomationProblem(500, "Operation failed", str(exc)) from exc

        envelope = self._envelope(
            ok=True,
            status="completed",
            operation_id=operation_id,
            request_id=request_id,
            result=result,
        )
        self._audit(
            principal=principal,
            operation_id=operation_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            input_payload=normalized_payload,
            envelope=envelope,
            approval_state="not_required",
        )
        return envelope

    def list_jobs(
        self,
        principal: AutomationPrincipal,
        request_id: str,
        limit: int = 100,
    ) -> AutomationEnvelope:
        if principal.role == "admin" or principal.has_scopes(["jobs:read"]):
            records = self.store.list_jobs(
                limit=limit,
                principal_type=None,
                principal_id=None,
            )
            if principal.role != "admin" and "*" not in principal.scopes:
                records = [
                    record
                    for record in records
                    if record["principal_type"] == principal.principal_type
                    and record["principal_id"] == principal.principal_id
                ]
        else:
            raise AutomationProblem(403, "Scope cannot access jobs", "jobs:read scope required")

        return self._envelope(
            ok=True,
            status="completed",
            operation_id="jobs.list",
            request_id=request_id,
            result=JobListResult(
                items=[self._serialize_job_record(record) for record in records]
            ).model_dump(mode="json"),
        )

    def get_job(
        self,
        principal: AutomationPrincipal,
        request_id: str,
        job_id: str,
    ) -> AutomationEnvelope:
        record = self.store.get_job(job_id)
        if not record:
            raise AutomationProblem(404, "Job not found", "Job not found")
        if principal.role != "admin" and "*" not in principal.scopes:
            if (
                record["principal_type"] != principal.principal_type
                or record["principal_id"] != principal.principal_id
            ):
                raise AutomationProblem(
                    403,
                    "Scope cannot access job",
                    "Cannot access a job owned by another principal",
                )
        return self._envelope(
            ok=True,
            status="completed",
            operation_id="jobs.get",
            request_id=request_id,
            job_id=job_id,
            result=self._serialize_job_record(record).model_dump(mode="json"),
        )

    def decide_approval(
        self,
        principal: AutomationPrincipal,
        approval_id: str,
        decision: ApprovalDecisionRequest,
        request_id: str,
    ) -> AutomationEnvelope:
        approval = self.store.get_approval(approval_id)
        if not approval:
            raise AutomationProblem(404, "Approval not found", "Approval not found")
        if approval["status"] != "pending":
            raise AutomationProblem(
                409,
                "Approval already decided",
                "Approval has already been decided",
            )
        if principal.role != "admin" and not principal.has_scopes({"approvals:manage"}):
            raise AutomationProblem(
                403,
                "Scope cannot decide approval",
                "approvals:manage scope required",
            )

        if decision.decision == "reject":
            record = self.store.update_approval(
                approval_id=approval_id,
                status="rejected",
                decision_reason=decision.reason,
                decided_by=principal.display_name,
            )
            if approval.get("job_id"):
                self.store.update_job(
                    job_id=approval["job_id"],
                    status="rejected",
                    error_payload={
                        "title": "Approval rejected",
                        "detail": decision.reason or "Operation was rejected",
                    },
                )
            if record is None:
                raise AutomationProblem(404, "Approval not found", "Approval not found")
            result = ApprovalResult(
                approval=self._serialize_approval_record(record)
            ).model_dump(mode="json")
            envelope = self._envelope(
                ok=True,
                status="rejected",
                operation_id=approval["operation_id"],
                request_id=request_id,
                approval_id=approval_id,
                result=result,
            )
            self._audit(
                principal=principal,
                operation_id="approvals.decide",
                request_id=request_id,
                idempotency_key=None,
                input_payload={"approval_id": approval_id, **decision.model_dump(mode="json")},
                envelope=envelope,
                approval_state="rejected",
            )
            return envelope

        operation = self._operations.get(approval["operation_id"])
        if not operation:
            raise AutomationProblem(404, "Operation not found", "Operation not found")

        job_id = approval.get("job_id") or f"job_{uuid.uuid4().hex[:12]}"
        existing_job = self.store.get_job(job_id)
        if existing_job is None:
            self.store.create_job(
                job_id=job_id,
                operation_id=approval["operation_id"],
                principal_type=approval["principal_type"],
                principal_id=approval["principal_id"],
                status="running",
                request_id=approval["request_id"],
                input_payload=approval["input"],
                approval_id=approval_id,
            )
        else:
            self.store.update_job(job_id=job_id, status="running")
        self.store.update_approval(
            approval_id=approval_id,
            status="approved",
            decision_reason=decision.reason,
            decided_by=principal.display_name,
            job_id=job_id,
        )

        operation_principal = self._rehydrate_principal(approval)

        try:
            typed_payload = operation.input_model.model_validate(approval["input"])
            result = operation.handler(typed_payload, operation_principal)
            job = self.store.update_job(
                job_id=job_id,
                status="completed",
                result_payload=result,
            )
        except AutomationProblem as exc:
            job = self.store.update_job(
                job_id=job_id,
                status="failed",
                error_payload={"title": exc.title, "detail": exc.detail},
            )
            if job is None:
                raise
            envelope = self._envelope(
                ok=False,
                status="failed",
                operation_id=approval["operation_id"],
                request_id=request_id,
                approval_id=approval_id,
                job_id=job_id,
                error=_problem(exc.status_code, exc.title, exc.detail, request_id),
                next_action=f"poll:{job_id}",
            )
            self._audit(
                principal=principal,
                operation_id="approvals.decide",
                request_id=request_id,
                idempotency_key=None,
                input_payload={"approval_id": approval_id, **decision.model_dump(mode="json")},
                envelope=envelope,
                approval_state="approved",
            )
            return envelope
        except Exception as exc:  # pragma: no cover - safety net
            job = self.store.update_job(
                job_id=job_id,
                status="failed",
                error_payload={"title": "Execution failed", "detail": str(exc)},
            )
            if job is None:
                raise AutomationProblem(500, "Execution failed", str(exc)) from exc
            envelope = self._envelope(
                ok=False,
                status="failed",
                operation_id=approval["operation_id"],
                request_id=request_id,
                approval_id=approval_id,
                job_id=job_id,
                error=_problem(500, "Execution failed", str(exc), request_id),
                next_action=f"poll:{job_id}",
            )
            self._audit(
                principal=principal,
                operation_id="approvals.decide",
                request_id=request_id,
                idempotency_key=None,
                input_payload={"approval_id": approval_id, **decision.model_dump(mode="json")},
                envelope=envelope,
                approval_state="approved",
            )
            return envelope

        serialized_job = self._serialize_job_record(job or self.store.get_job(job_id) or {})
        envelope = self._envelope(
            ok=True,
            status="completed",
            operation_id=approval["operation_id"],
            request_id=request_id,
            approval_id=approval_id,
            job_id=job_id,
            result=serialized_job.model_dump(mode="json"),
            next_action=f"poll:{job_id}",
        )
        self._audit(
            principal=principal,
            operation_id="approvals.decide",
            request_id=request_id,
            idempotency_key=None,
            input_payload={"approval_id": approval_id, **decision.model_dump(mode="json")},
            envelope=envelope,
            approval_state="approved",
        )
        return envelope

    def list_service_accounts(
        self, principal: AutomationPrincipal, request_id: str
    ) -> AutomationEnvelope:
        self._require_management_scope(principal, "service_accounts:read")
        records = [
            self.serialize_service_account(record).model_dump(mode="json")
            for record in self.auth.list_service_accounts(include_revoked=True)
        ]
        return self._envelope(
            ok=True,
            status="completed",
            operation_id="service_accounts.list",
            request_id=request_id,
            result=ServiceAccountListResult(items=records).model_dump(mode="json"),
        )

    def create_service_account(
        self,
        principal: AutomationPrincipal,
        request_id: str,
        payload: ServiceAccountCreateRequest,
    ) -> AutomationEnvelope:
        self._require_management_scope(principal, "service_accounts:write")
        try:
            normalized_scopes = normalize_service_account_scopes(
                payload.role, payload.scopes
            )
        except ValueError as exc:
            raise AutomationProblem(422, "Validation failed", str(exc)) from exc

        try:
            record, token = self.auth.create_service_account(
                name=payload.name,
                role=payload.role,
                scopes=normalized_scopes,
                description=payload.description,
                expires_in_seconds=payload.expires_in_seconds,
            )
        except Exception as exc:
            raise AutomationProblem(
                409,
                "Service account creation failed",
                str(exc),
            ) from exc

        secret = ServiceAccountSecret(
            **self.serialize_service_account(record).model_dump(),
            token=token,
        )
        envelope = self._envelope(
            ok=True,
            status="completed",
            operation_id="service_accounts.create",
            request_id=request_id,
            result=secret.model_dump(mode="json"),
        )
        self._audit(
            principal=principal,
            operation_id="service_accounts.create",
            request_id=request_id,
            idempotency_key=None,
            input_payload=payload.model_dump(mode="json"),
            envelope=envelope,
            approval_state="not_required",
        )
        return envelope

    def rotate_service_account(
        self,
        principal: AutomationPrincipal,
        request_id: str,
        account_id: str,
        expires_in_seconds: int | None = None,
    ) -> AutomationEnvelope:
        self._require_management_scope(principal, "service_accounts:write")
        rotated = self.auth.rotate_service_account(
            account_id=account_id,
            expires_in_seconds=expires_in_seconds,
        )
        if rotated is None:
            raise AutomationProblem(
                404,
                "Service account not found",
                "Service account not found",
            )
        record, token = rotated
        secret = ServiceAccountSecret(
            **self.serialize_service_account(record).model_dump(),
            token=token,
        )
        envelope = self._envelope(
            ok=True,
            status="completed",
            operation_id="service_accounts.rotate",
            request_id=request_id,
            result=secret.model_dump(mode="json"),
        )
        self._audit(
            principal=principal,
            operation_id="service_accounts.rotate",
            request_id=request_id,
            idempotency_key=None,
            input_payload={
                "account_id": account_id,
                "expires_in_seconds": expires_in_seconds,
            },
            envelope=envelope,
            approval_state="not_required",
        )
        return envelope

    def revoke_service_account(
        self,
        principal: AutomationPrincipal,
        request_id: str,
        account_id: str,
    ) -> AutomationEnvelope:
        self._require_management_scope(principal, "service_accounts:write")
        record = self.auth.revoke_service_account(account_id)
        if record is None:
            raise AutomationProblem(
                404,
                "Service account not found",
                "Service account not found",
            )
        envelope = self._envelope(
            ok=True,
            status="completed",
            operation_id="service_accounts.revoke",
            request_id=request_id,
            result=self.serialize_service_account(record).model_dump(mode="json"),
        )
        self._audit(
            principal=principal,
            operation_id="service_accounts.revoke",
            request_id=request_id,
            idempotency_key=None,
            input_payload={"account_id": account_id},
            envelope=envelope,
            approval_state="not_required",
        )
        return envelope
