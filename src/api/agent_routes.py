"""Agent-facing REST routes for SupportOID automation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from src.app.auth import (
    AutomationPrincipal,
    get_management_principal,
    get_service_account_principal,
)
from src.app.automation import AutomationProblem, AutomationService
from src.app.automation_dto import (
    ApprovalDecisionRequest,
    AutomationEnvelope,
    InvokeRequest,
    ServiceAccountCreateRequest,
)
from src.app.dto import ProblemDetail


router = APIRouter(prefix="/api/v1/agent", tags=["supportoid-agent"])


def _automation(request: Request) -> AutomationService:
    return request.app.state.automation


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _raise_problem(problem: AutomationProblem, request_id: str) -> None:
    raise HTTPException(
        status_code=problem.status_code,
        detail=ProblemDetail(
            type=f"https://supportoid.dev/errors/{problem.status_code}",
            title=problem.title,
            status=problem.status_code,
            detail=problem.detail,
            request_id=request_id,
        ).model_dump(mode="json"),
    )


@router.get("/capabilities", response_model=AutomationEnvelope)
async def capabilities(
    request: Request,
    principal: AutomationPrincipal = Depends(get_service_account_principal),
):
    automation = _automation(request)
    return automation.list_capabilities(principal, _request_id(request))


@router.post("/invoke", response_model=AutomationEnvelope)
async def invoke(
    payload: InvokeRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: AutomationPrincipal = Depends(get_service_account_principal),
):
    automation = _automation(request)
    try:
        return automation.invoke(
            principal,
            payload.operation_id,
            payload.input,
            request_id=payload.request_id or _request_id(request),
            idempotency_key=idempotency_key,
            approval_mode=payload.approval_mode,
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.get("/jobs", response_model=AutomationEnvelope)
async def list_jobs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    principal: AutomationPrincipal = Depends(get_service_account_principal),
):
    automation = _automation(request)
    try:
        return automation.list_jobs(
            principal,
            _request_id(request),
            limit=limit,
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.get("/jobs/{job_id}", response_model=AutomationEnvelope)
async def get_job(
    job_id: str,
    request: Request,
    principal: AutomationPrincipal = Depends(get_service_account_principal),
):
    automation = _automation(request)
    try:
        return automation.get_job(principal, _request_id(request), job_id)
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.post("/approvals/{approval_id}/decision", response_model=AutomationEnvelope)
async def approval_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    principal: AutomationPrincipal = Depends(get_management_principal),
):
    automation = _automation(request)
    try:
        return automation.decide_approval(
            principal=principal,
            approval_id=approval_id,
            decision=payload,
            request_id=_request_id(request),
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.get("/service-accounts", response_model=AutomationEnvelope)
async def list_service_accounts(
    request: Request,
    principal: AutomationPrincipal = Depends(get_management_principal),
):
    automation = _automation(request)
    try:
        return automation.list_service_accounts(principal, _request_id(request))
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.post("/service-accounts", response_model=AutomationEnvelope)
async def create_service_account(
    payload: ServiceAccountCreateRequest,
    request: Request,
    principal: AutomationPrincipal = Depends(get_management_principal),
):
    automation = _automation(request)
    try:
        return automation.create_service_account(
            principal=principal,
            request_id=_request_id(request),
            payload=payload,
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.post("/service-accounts/{account_id}/rotate", response_model=AutomationEnvelope)
async def rotate_service_account(
    account_id: str,
    request: Request,
    expires_in_seconds: int | None = Query(default=None, ge=60, le=31_536_000),
    principal: AutomationPrincipal = Depends(get_management_principal),
):
    automation = _automation(request)
    try:
        return automation.rotate_service_account(
            principal=principal,
            request_id=_request_id(request),
            account_id=account_id,
            expires_in_seconds=expires_in_seconds,
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))


@router.post("/service-accounts/{account_id}/revoke", response_model=AutomationEnvelope)
async def revoke_service_account(
    account_id: str,
    request: Request,
    principal: AutomationPrincipal = Depends(get_management_principal),
):
    automation = _automation(request)
    try:
        return automation.revoke_service_account(
            principal=principal,
            request_id=_request_id(request),
            account_id=account_id,
        )
    except AutomationProblem as problem:
        _raise_problem(problem, _request_id(request))
