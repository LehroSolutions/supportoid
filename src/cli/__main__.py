"""SupportOID CLI: human and agent-facing command surface."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.app.auth import AuthService, to_automation_principal
from src.app.automation import AutomationProblem, AutomationService
from src.app.automation_dto import ApprovalDecisionRequest, InvokeRequest
from src.app.automation_store import AutomationStore
from src.app.dto import ChatRequest, FeedbackRequest, ProblemDetail
from src.app.service import SupportOIDService
from src.config.settings import Settings

EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_AUTH = 3
EXIT_PERMISSION = 4
EXIT_RATE_LIMIT = 5
EXIT_APPROVAL = 6
EXIT_INTERNAL = 10


class CLIError(Exception):
    """Structured CLI error with exit code and optional detail payload."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int = EXIT_INTERNAL,
        detail: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.exit_code = exit_code
        self.detail = detail or {
            "type": "https://supportoid.dev/errors/cli",
            "title": "CLI Error",
            "status": 500,
            "detail": message,
        }


def _problem_to_exit_code(problem: dict[str, Any]) -> int:
    status = int(problem.get("status", 500) or 500)
    if status in {400, 409, 422}:
        return EXIT_VALIDATION
    if status == 401:
        return EXIT_AUTH
    if status == 403:
        return EXIT_PERMISSION
    if status == 429:
        return EXIT_RATE_LIMIT
    return EXIT_INTERNAL


def _envelope_to_exit_code(payload: dict[str, Any]) -> int:
    if payload.get("status") == "approval_required":
        return EXIT_APPROVAL
    if payload.get("ok") is False:
        error = payload.get("error") or {}
        return _problem_to_exit_code(error)
    return EXIT_OK


def _parse_json_input(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CLIError(
            "Input must be valid JSON",
            exit_code=EXIT_VALIDATION,
            detail={
                "type": "https://supportoid.dev/errors/validation",
                "title": "Validation failed",
                "status": 422,
                "detail": str(exc),
            },
        ) from exc
    if not isinstance(payload, dict):
        raise CLIError(
            "Input JSON must be an object",
            exit_code=EXIT_VALIDATION,
            detail={
                "type": "https://supportoid.dev/errors/validation",
                "title": "Validation failed",
                "status": 422,
                "detail": "Input JSON must decode to an object",
            },
        )
    return payload


def _dump_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)


def _write_stdout(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        sys.stdout.write(json.dumps(payload))
        sys.stdout.write("\n")
        return
    sys.stdout.write(_dump_text(payload))
    sys.stdout.write("\n")


def _write_stderr(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        sys.stderr.write(json.dumps(payload))
        sys.stderr.write("\n")
        return
    sys.stderr.write(_dump_text(payload))
    sys.stderr.write("\n")


def _request_id(value: str | None) -> str:
    return value or f"cli_{uuid.uuid4().hex[:12]}"


@dataclass
class LocalAutomationRunner:
    automation: AutomationService

    @classmethod
    def from_settings(cls, settings: Settings) -> "LocalAutomationRunner":
        service = SupportOIDService(settings)
        store = AutomationStore(settings.sqlite_path)
        auth = AuthService(
            users=settings.auth_users,
            session_ttl_seconds=settings.session_ttl_seconds,
            cookie_name=settings.session_cookie_name,
            secure_cookies=settings.deployment_profile == "production",
            automation_store=store,
            agent_token_ttl_seconds=settings.agent_token_ttl_seconds,
            allow_password_fallback=settings.deployment_profile == "test",
        )
        automation = AutomationService(
            service=service,
            auth=auth,
            store=store,
            start_time_provider=time.time,
        )
        return cls(automation=automation)

    def capabilities(self, request_id: str) -> dict[str, Any]:
        principal = to_automation_principal(local=True)
        return self.automation.list_capabilities(
            principal,
            request_id,
        ).model_dump(mode="json")

    def invoke(
        self,
        payload: InvokeRequest,
        *,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        principal = to_automation_principal(local=True)
        return self.automation.invoke(
            principal,
            payload.operation_id,
            payload.input,
            request_id=request_id,
            idempotency_key=idempotency_key,
            approval_mode=payload.approval_mode,
        ).model_dump(mode="json")

    def jobs_list(self, request_id: str) -> dict[str, Any]:
        principal = to_automation_principal(local=True)
        return self.automation.list_jobs(principal, request_id).model_dump(mode="json")

    def jobs_get(self, job_id: str, request_id: str) -> dict[str, Any]:
        principal = to_automation_principal(local=True)
        return self.automation.get_job(
            principal,
            request_id,
            job_id,
        ).model_dump(mode="json")

    def approve(
        self,
        approval_id: str,
        decision: ApprovalDecisionRequest,
        request_id: str,
    ) -> dict[str, Any]:
        principal = to_automation_principal(local=True)
        return self.automation.decide_approval(
            principal=principal,
            approval_id=approval_id,
            decision=decision,
            request_id=request_id,
        ).model_dump(mode="json")


@dataclass
class RemoteAutomationRunner:
    base_url: str
    token: str

    def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Request-ID": request_id,
        }
        if headers:
            request_headers.update(headers)
        data = None
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            detail = json.loads(raw) if raw else {
                "type": f"https://supportoid.dev/errors/{exc.code}",
                "title": "HTTP Error",
                "status": exc.code,
                "detail": exc.reason,
            }
            raise CLIError(
                detail.get("detail", exc.reason),
                exit_code=_problem_to_exit_code(detail),
                detail=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise CLIError(
                f"Remote request failed: {exc.reason}",
                detail={
                    "type": "https://supportoid.dev/errors/network",
                    "title": "Network error",
                    "status": 503,
                    "detail": str(exc.reason),
                },
            ) from exc

    def capabilities(self, request_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/agent/capabilities",
            request_id=request_id,
        )

    def invoke(
        self,
        payload: InvokeRequest,
        *,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._request(
            "POST",
            "/api/v1/agent/invoke",
            request_id=request_id,
            body=payload.model_dump(mode="json"),
            headers=headers,
        )

    def jobs_list(self, request_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/agent/jobs",
            request_id=request_id,
        )

    def jobs_get(self, job_id: str, request_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/api/v1/agent/jobs/{job_id}",
            request_id=request_id,
        )

    def approve(
        self,
        approval_id: str,
        decision: ApprovalDecisionRequest,
        request_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/agent/approvals/{approval_id}/decision",
            request_id=request_id,
            body=decision.model_dump(mode="json"),
        )


class SupportCLI:
    """Legacy CLI facade over the canonical SupportOIDService."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.base = Path(__file__).parent.parent.parent
        self._service: SupportOIDService | None = None

    @property
    def service(self) -> SupportOIDService:
        if self._service is None:
            self._service = SupportOIDService(self.settings)
        return self._service

    def _auth_service(self) -> AuthService:
        store = AutomationStore(self.settings.sqlite_path)
        return AuthService(
            users=self.settings.auth_users,
            session_ttl_seconds=self.settings.session_ttl_seconds,
            cookie_name=self.settings.session_cookie_name,
            secure_cookies=self.settings.deployment_profile == "production",
            automation_store=store,
            agent_token_ttl_seconds=self.settings.agent_token_ttl_seconds,
            allow_password_fallback=self.settings.deployment_profile == "test",
        )

    def diagnose(self) -> str:
        payload = self.service.diagnose()
        return json.dumps(payload, indent=2)

    def fix(self, component: str | None = None) -> str:
        if component:
            return (
                f"No auto-fix routine configured for '{component}'. "
                "Use 'migrate' or 'sync'."
            )
        return "Auto-fix not required: canonical core initialized."

    def status(self) -> str:
        stats = self.service.get_stats_report()
        return json.dumps(stats.model_dump(), indent=2)

    def traces(self) -> str:
        traces = self.service.list_trace_summaries(limit=100)
        if not traces:
            return "No workflow traces found."
        lines = [
            f"{'Session':<24} {'Duration':<10} {'Steps':<8} {'Escalated':<10} {'Error'}"
        ]
        lines.append("-" * 78)
        for item in traces:
            lines.append(
                f"{item.session_id:<24} {item.duration_s:<10.3f} {item.steps:<8} "
                f"{'Yes' if item.escalated else 'No':<10} {item.error or '-'}"
            )
        return "\n".join(lines)

    def trace(self, session_id: str | None = None) -> str:
        if not session_id:
            return self.traces()
        trace = self.service.get_trace(session_id)
        if not trace:
            return f"No trace found for session: {session_id}"
        return json.dumps(trace, indent=2)

    def costs(self, conversation_id: str | None = None) -> str:
        summary = self.service.get_cost_summary(conversation_id)
        return json.dumps(summary.model_dump(), indent=2)

    def migrate(self) -> str:
        return json.dumps(self.service.migrate_legacy_data(), indent=2)

    def sync(self, limit: int = 100) -> str:
        return json.dumps(self.service.run_sync(limit=limit), indent=2)

    def chat(self, message: str, conversation_id: str | None = None) -> str:
        response = self.service.chat(
            ChatRequest(message=message, conversation_id=conversation_id),
            actor="support",
        )
        return json.dumps(response.model_dump(), indent=2, default=str)

    def feedback(
        self,
        conversation_id: str,
        rating: int,
        text: str = "",
        corrected_intent: str = "",
    ) -> str:
        ack = self.service.record_feedback(
            FeedbackRequest(
                conversation_id=conversation_id,
                rating=rating,
                feedback_text=text,
                corrected_intent=corrected_intent,
            )
        )
        return json.dumps(ack.model_dump(), indent=2)

    def bootstrap_admin(self, username: str, password: str) -> str:
        auth = self._auth_service()
        record = auth.bootstrap_admin(username=username, password=password)
        return json.dumps(
            {
                "status": "created",
                "user": {
                    "username": record.get("username", username),
                    "role": record.get("role", "admin"),
                },
                "sqlite_path": self.settings.sqlite_path,
            },
            indent=2,
        )

    def seed_demo(self, overwrite: bool = False) -> str:
        seed_root = Path(self.settings.seed_dir) / "knowledge"
        if not seed_root.exists():
            raise CLIError(
                f"Seed directory not found: {seed_root}",
                exit_code=EXIT_VALIDATION,
            )
        target_root = Path(self.settings.kb_dir)
        target_root.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        for source in sorted(seed_root.glob("*.json")):
            destination = target_root / source.name
            if destination.exists() and not overwrite:
                skipped += 1
                continue
            shutil.copy2(source, destination)
            copied += 1

        return json.dumps(
            {
                "status": "seeded",
                "copied": copied,
                "skipped": skipped,
                "source": str(seed_root),
                "target": str(target_root),
                "overwrite": overwrite,
            },
            indent=2,
        )

    def run_legacy_models(self, args: list[str]) -> str:
        from src.cli.commands.models import run_command

        return run_command(args)

    def run_legacy_voice(self, args: list[str]) -> str:
        from src.cli.commands.voice import run_command

        return run_command(args)

    def run_legacy_costs(self, args: list[str]) -> str:
        from src.cli.commands.costs import run_command

        return run_command(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SupportOID CLI")
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--token", default="")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--request-id", default=None)
    parser.add_argument("--wait", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities")

    invoke_parser = subparsers.add_parser("invoke")
    invoke_parser.add_argument("operation_id")
    invoke_parser.add_argument("--input", default="{}")
    invoke_parser.add_argument("--approval-mode", default=None)

    jobs_parser = subparsers.add_parser("jobs")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", required=True)
    jobs_subparsers.add_parser("list")
    jobs_get_parser = jobs_subparsers.add_parser("get")
    jobs_get_parser.add_argument("job_id")

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("approval_id")
    approve_parser.add_argument(
        "--decision",
        choices=["approve", "reject"],
        default="approve",
    )
    approve_parser.add_argument("--reason", default="")

    bootstrap_parser = subparsers.add_parser("bootstrap-admin")
    bootstrap_parser.add_argument("--username", required=True)
    bootstrap_parser.add_argument("--password", required=True)

    seed_parser = subparsers.add_parser("seed-demo")
    seed_parser.add_argument("--overwrite", action="store_true")

    legacy_commands = [
        "diagnose",
        "fix",
        "status",
        "trace",
        "traces",
        "models",
        "voice",
        "costs",
        "serve",
        "migrate",
        "sync",
        "chat",
        "feedback",
        "test",
    ]
    for command in legacy_commands:
        subparsers.add_parser(command)

    parser.add_argument("--component", default=None)
    parser.add_argument("--session", default=None)
    parser.add_argument("--conversation", default=None)
    parser.add_argument("--rating", type=int, default=5)
    parser.add_argument("--feedback-text", default="")
    parser.add_argument("--corrected-intent", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--args", default="")
    parser.add_argument("--limit", type=int, default=100)
    return parser


def _automation_runner(args: argparse.Namespace, settings: Settings):
    if args.mode == "remote":
        if not args.token:
            raise CLIError(
                "Remote mode requires --token",
                exit_code=EXIT_AUTH,
                detail={
                    "type": "https://supportoid.dev/errors/auth",
                    "title": "Authentication required",
                    "status": 401,
                    "detail": "Remote mode requires a bearer token",
                },
            )
        return RemoteAutomationRunner(base_url=args.base_url, token=args.token)
    return LocalAutomationRunner.from_settings(settings)


def _poll_job(
    runner: LocalAutomationRunner | RemoteAutomationRunner,
    job_id: str,
    request_id: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last = runner.jobs_get(job_id, request_id)
    while time.monotonic() < deadline:
        job = last.get("result") or {}
        status = job.get("status")
        if status not in {"queued", "running", "waiting_approval"}:
            return last
        time.sleep(0.2)
        last = runner.jobs_get(job_id, request_id)
    return last


def _run_automation_command(
    args: argparse.Namespace,
    settings: Settings,
) -> dict[str, Any]:
    runner = _automation_runner(args, settings)
    request_id = _request_id(args.request_id)

    try:
        if args.command == "capabilities":
            return runner.capabilities(request_id)

        if args.command == "invoke":
            payload = InvokeRequest(
                operation_id=args.operation_id,
                input=_parse_json_input(args.input),
                request_id=request_id,
                approval_mode=args.approval_mode,
            )
            response = runner.invoke(
                payload,
                request_id=request_id,
                idempotency_key=args.idempotency_key,
            )
            if args.wait and response.get("job_id"):
                status = response.get("status")
                if status in {"queued", "running"}:
                    response = _poll_job(runner, response["job_id"], request_id)
            return response

        if args.command == "jobs" and args.jobs_command == "list":
            return runner.jobs_list(request_id)

        if args.command == "jobs" and args.jobs_command == "get":
            return runner.jobs_get(args.job_id, request_id)

        if args.command == "approve":
            decision = ApprovalDecisionRequest(
                decision=args.decision,
                reason=args.reason,
            )
            response = runner.approve(args.approval_id, decision, request_id)
            if args.wait and response.get("job_id"):
                response = _poll_job(runner, response["job_id"], request_id)
            return response
    except AutomationProblem as problem:
        detail = ProblemDetail(
            type=f"https://supportoid.dev/errors/{problem.status_code}",
            title=problem.title,
            status=problem.status_code,
            detail=problem.detail,
            request_id=request_id,
        ).model_dump(mode="json")
        raise CLIError(
            problem.detail,
            exit_code=_problem_to_exit_code(detail),
            detail=detail,
        ) from problem

    raise CLIError("Unsupported automation command")


def _run_legacy_command(
    args: argparse.Namespace,
    unknown: list[str],
    settings: Settings,
) -> str:
    cli = SupportCLI(settings)

    if args.command == "diagnose":
        return cli.diagnose()
    if args.command == "bootstrap-admin":
        return cli.bootstrap_admin(args.username, args.password)
    if args.command == "fix":
        return cli.fix(args.component)
    if args.command == "status":
        return cli.status()
    if args.command == "trace":
        return cli.trace(args.session)
    if args.command == "traces":
        return cli.traces()
    if args.command == "models":
        legacy_args = args.args.split() if args.args else []
        legacy_args.extend(unknown)
        return cli.run_legacy_models(legacy_args)
    if args.command == "voice":
        legacy_args = args.args.split() if args.args else []
        legacy_args.extend(unknown)
        return cli.run_legacy_voice(legacy_args)
    if args.command == "costs":
        extra = args.args.split() if args.args else []
        extra.extend(unknown)
        if args.conversation and "--conversation" not in extra:
            extra = ["--conversation", args.conversation, *extra]
        return cli.run_legacy_costs(extra)
    if args.command == "serve":
        from src.main import run

        run()
        return ""
    if args.command == "migrate":
        return cli.migrate()
    if args.command == "sync":
        return cli.sync(limit=args.limit)
    if args.command == "seed-demo":
        return cli.seed_demo(overwrite=args.overwrite)
    if args.command == "chat":
        if not args.message:
            raise CLIError(
                "--message is required for chat",
                exit_code=EXIT_VALIDATION,
            )
        return cli.chat(args.message, conversation_id=args.conversation)
    if args.command == "feedback":
        if not args.conversation:
            raise CLIError(
                "--conversation is required for feedback",
                exit_code=EXIT_VALIDATION,
            )
        return cli.feedback(
            args.conversation,
            args.rating,
            text=args.feedback_text,
            corrected_intent=args.corrected_intent,
        )
    if args.command == "test":
        gate_tests = [
            "tests/test_stabilized_core_gate.py",
            "tests/test_api_contracts_v1.py",
            "tests/test_agent_api_cli.py",
        ]
        command = [sys.executable, "-m", "pytest", *gate_tests, "-q", "--tb=short"]
        result = subprocess.run(command, text=True)
        raise SystemExit(result.returncode)

    raise CLIError("Unsupported command")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args, unknown = parser.parse_known_args(argv)
    if args.json:
        args.format = "json"

    settings = Settings.from_env()

    try:
        if args.command in {"capabilities", "invoke", "jobs", "approve"}:
            payload = _run_automation_command(args, settings)
            _write_stdout(payload, args.format)
            return _envelope_to_exit_code(payload)

        output = _run_legacy_command(args, unknown, settings)
        if output:
            sys.stdout.write(output)
            if not output.endswith("\n"):
                sys.stdout.write("\n")
        return EXIT_OK
    except CLIError as exc:
        _write_stderr(exc.detail, args.format)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
