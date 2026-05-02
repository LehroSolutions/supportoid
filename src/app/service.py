"""Canonical SupportOID application service layer."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.agents.cost_tracker import CostTracker
from src.agents.kb_quality import KBQualityScorer
from src.agents.trace_summary import summarize_single_trace
from src.app.auth import AuthService
from src.app.dto import (
    ChatRequest,
    ChatResponse,
    CostSummary,
    FeedbackAck,
    FeedbackRequest,
    KBQualityReport,
    PaginationResponse,
    StatsReport,
    TraceSummary,
)
from src.app.storage import HybridStore, import_legacy_json
from src.config.settings import Settings


class SupportOIDService:
    """Single canonical backend for CLI, API, and web."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = HybridStore(
            sqlite_path=settings.sqlite_path,
            convex_adapter_url=settings.convex_adapter_url,
            convex_api_key=settings.convex_api_key,
        )
        self.store.prune_retention(
            trace_retention_days=settings.trace_retention_days,
            feedback_retention_days=settings.feedback_retention_days,
        )
        self.cost_tracker = CostTracker(settings.cost_dir)
        self.kb_quality = KBQualityScorer(settings.kb_dir, settings.feedback_dir)
        self.orchestrator = self._build_orchestrator()

    def _build_orchestrator(self):
        try:
            from src.agents.enhanced_orchestrator import EnhancedOrchestrator

            return EnhancedOrchestrator(self.settings, store=self.store)
        except Exception:
            from src.orchestrator import Orchestrator

            orch = Orchestrator(self.settings, store=self.store)
            orch.initialize()
            return orch

    def chat(self, req: ChatRequest, actor: str = "support") -> ChatResponse:
        conversation_id = req.conversation_id or ""
        user_id = req.user_id or actor
        started = time.monotonic()

        try:
            raw = self.orchestrator.process(
                req.message,
                conversation_id=conversation_id or None,
                user_id=user_id,
                tier=req.tier,
            )
        except TypeError:
            raw = self.orchestrator.process(
                req.message,
                conversation_id=conversation_id or None,
                user_id=user_id,
            )

        response = ChatResponse(
            conversation_id=raw.get("conversation_id", conversation_id or "conv_unknown"),
            response=raw.get("response", ""),
            intent=raw.get("intent", "general_question"),
            confidence=float(raw.get("confidence", 0.0) or 0.0),
            sentiment=float(raw.get("sentiment", 0.0) or 0.0),
            urgency=float(raw.get("urgency", 0.0) or 0.0),
            tone=raw.get("tone", "warm"),
            quality_score=float(raw.get("quality_score", 0.0) or 0.0),
            should_escalate=bool(raw.get("should_escalate", False)),
            escalation_reason=raw.get("escalation_reason", "") or "",
            source=raw.get("source", "unknown"),
            kb_results_used=int(raw.get("kb_results_used", 0) or 0),
            suggested_actions=list(raw.get("suggested_actions", []) or []),
            processing_time_ms=float(raw.get("processing_time_ms", 0.0) or 0.0),
            role=getattr(actor, "role", "support") if hasattr(actor, "role") else "support",
        )

        if response.processing_time_ms <= 0:
            response.processing_time_ms = round((time.monotonic() - started) * 1000, 1)

        trace_payload = {
            "session_id": response.conversation_id,
            "user_input": req.message,
            "duration_s": round(response.processing_time_ms / 1000.0, 3),
            "duration": round(response.processing_time_ms / 1000.0, 3),
            "steps": [
                {"agent": "classifier", "action": "classify", "status": "success"},
                {"agent": "knowledge", "action": "search", "status": "success"},
                {
                    "agent": "response",
                    "action": "generate",
                    "status": "success",
                    "engine": "support_response",
                    "model_profile": raw.get("model_profile"),
                    "transport": raw.get("transport"),
                },
                {"agent": "quality", "action": "score", "status": "success"},
            ],
            "error": raw.get("error"),
            "model": raw.get("model_name", raw.get("source", "unknown")),
            "cost": raw.get("cost_usd"),
            "tokens": raw.get("tokens"),
            "response_preview": response.response[:300],
            "model_profile": raw.get("model_profile"),
            "model_family": raw.get("model_family"),
            "transport": raw.get("transport"),
            "fallback_used": bool(raw.get("fallback_used", False)),
            "grounding_ids": list(raw.get("grounding_ids", []) or []),
            "response_id": raw.get("response_id"),
            "attempts": list(raw.get("attempts", []) or []),
        }
        self.store.save_trace(trace_payload)

        model_name = raw.get("model_name")
        if model_name:
            cost_row = self.cost_tracker.record(
                response.conversation_id,
                model_name,
                int(raw.get("input_tokens", 0) or 0),
                int(raw.get("output_tokens", 0) or 0),
                float(raw.get("processing_time_ms", response.processing_time_ms) or 0),
            )
            convo_cost = self.cost_tracker.get_conversation(response.conversation_id)
            if convo_cost:
                self.store.save_cost(response.conversation_id, convo_cost)
                self.cost_tracker.save_conversation(response.conversation_id)

        return response

    def record_feedback(self, req: FeedbackRequest) -> FeedbackAck:
        retrain = None
        if hasattr(self.orchestrator, "submit_feedback"):
            retrain = self.orchestrator.submit_feedback(
                req.conversation_id,
                req.rating,
                req.feedback_text,
                req.corrected_intent,
            )
        elif hasattr(self.orchestrator, "original") and hasattr(
            self.orchestrator.original, "submit_feedback"
        ):
            retrain = self.orchestrator.original.submit_feedback(
                req.conversation_id,
                req.rating,
                req.feedback_text,
                req.corrected_intent,
            )
        payload = {
            "conversation_id": req.conversation_id,
            "rating": req.rating,
            "feedback_text": req.feedback_text,
            "corrected_intent": req.corrected_intent,
            "timestamp": time.time(),
        }
        self.store.save_feedback(payload)
        return FeedbackAck(
            status="recorded",
            conversation_id=req.conversation_id,
            rating=req.rating,
            retrain=retrain if isinstance(retrain, dict) else None,
            message="Feedback recorded",
        )

    def list_trace_summaries(self, limit: int = 50) -> List[TraceSummary]:
        traces = self.store.list_traces(limit=limit)
        summaries: List[TraceSummary] = []
        for trace in traces:
            summary = summarize_single_trace(trace)
            summaries.append(
                TraceSummary(
                    session_id=summary.get("session_id", "unknown"),
                    duration_s=float(summary.get("duration_s", 0) or 0),
                    steps=int(summary.get("total_steps", 0) or 0),
                    error=trace.get("error"),
                    user_input=trace.get("user_input", ""),
                    summary=summary.get("summary", ""),
                    escalated=bool(summary.get("escalated", False)),
                )
            )
        return summaries

    def list_trace_page(self, limit: int = 50, offset: int = 0) -> PaginationResponse:
        requested = max(limit + offset + 1, limit + 1)
        all_traces = self.list_trace_summaries(limit=requested)
        window = all_traces[offset : offset + limit + 1]
        has_more = len(window) > limit
        items = window[:limit]
        return PaginationResponse(
            items=[item.model_dump() for item in items],
            total=offset + len(items) + (1 if has_more else 0),
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def get_trace(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_trace(session_id)

    def get_cost_summary(self, conversation_id: Optional[str] = None) -> CostSummary:
        if conversation_id:
            convo = self.cost_tracker.get_conversation(conversation_id)
            if not convo:
                return CostSummary(conversation_id=conversation_id)
            return CostSummary(
                conversation_id=conversation_id,
                total_conversations=1,
                total_cost_usd=float(convo.get("total_cost_usd", 0.0)),
                total_calls=int(convo.get("call_count", 0)),
                total_input_tokens=int(convo.get("total_input_tokens", 0)),
                total_output_tokens=int(convo.get("total_output_tokens", 0)),
                calls_by_model=dict(convo.get("models_used", {})),
            )

        stats = self.cost_tracker.get_all_stats()
        return CostSummary(
            total_conversations=int(stats.get("total_conversations", 0)),
            total_cost_usd=float(stats.get("total_cost_usd", 0.0)),
            total_calls=int(stats.get("total_calls", 0)),
            total_input_tokens=int(stats.get("total_input_tokens", 0)),
            total_output_tokens=int(stats.get("total_output_tokens", 0)),
            cost_by_model=dict(stats.get("cost_by_model", {})),
            calls_by_model=dict(stats.get("calls_by_model", {})),
        )

    def get_kb_quality_report(self) -> KBQualityReport:
        report = self.kb_quality.score_all()
        return KBQualityReport(
            total_entries=int(report.get("total_entries", 0)),
            overall_avg=float(report.get("overall_avg", 0.0)),
            grade_distribution=dict(report.get("grade_distribution", {})),
            dimension_averages=dict(report.get("dimension_averages", {})),
            top_entries=dict(report.get("top_entries", {})),
            needs_attention=dict(report.get("needs_attention", {})),
            report_generated=report.get("report_generated"),
        )

    def get_stats_report(self) -> StatsReport:
        raw = self.orchestrator.get_stats() if hasattr(self.orchestrator, "get_stats") else {}
        store_stats = self.store.stats()
        costs = self.get_cost_summary()
        return StatsReport(
            version=str(raw.get("version", "v1")),
            total_processed=int(raw.get("total_processed", 0)),
            escalations=int(raw.get("escalations", 0)),
            avg_confidence=float(raw.get("avg_confidence", 0.0)),
            avg_quality=float(raw.get("avg_quality", 0.0)),
            active_sessions=int(raw.get("active_sessions", 0)),
            model_version=int(raw.get("model_version", 0)),
            model_accuracy=float(raw.get("model_accuracy", 0.0)),
            knowledge_entries=int(raw.get("knowledge_entries", 0)),
            feedback_records=int(raw.get("feedback_records", 0)),
            cache_hit_rate=float(raw.get("cache_hit_rate", 0.0)),
            errors=int(raw.get("errors", 0)),
            traces=int(store_stats.get("traces", 0)),
            costs=costs,
            active_model_profile=str(raw.get("active_model_profile", "") or ""),
            active_model_family=str(raw.get("active_model_family", "") or ""),
            llm_transport=str(raw.get("llm_transport", "") or ""),
            configured_model_chain=list(raw.get("configured_model_chain", []) or []),
            fallback_events=int(raw.get("fallback_events", 0) or 0),
        )

    def run_sync(self, limit: int = 100) -> Dict[str, Any]:
        sync = self.store.sync(limit=limit)
        return {
            "attempted": sync.attempted,
            "synced": sync.synced,
            "failed": sync.failed,
            "errors": sync.errors,
        }

    def migrate_legacy_data(self) -> Dict[str, Any]:
        imported = import_legacy_json(
            self.store,
            traces_dir=self.settings.trace_dir,
            feedback_dir=self.settings.feedback_dir,
            costs_dir=self.settings.cost_dir,
        )
        sync_result = self.run_sync(limit=500)
        return {"imported": imported, "sync": sync_result}

    def diagnose(self) -> Dict[str, Any]:
        trace_count = len(self.store.list_traces(limit=500))
        quality = self.get_kb_quality_report()
        return {
            "python": {"status": "ok"},
            "orchestrator": {"status": "ok", "class": self.orchestrator.__class__.__name__},
            "storage": {"status": "ok", **self.store.stats()},
            "traces": {"status": "ok", "count": trace_count},
            "kb_quality": {"status": "ok", "overall_avg": quality.overall_avg},
        }

    def get_health_report(
        self, auth: AuthService, start_time: float | None = None
    ) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        convex_ok = None
        circuit_state = "disabled"
        llm_runtime: Dict[str, Any] = {}
        if orch and hasattr(orch, "original"):
            store = getattr(orch.original, "store", None)
            if store and hasattr(store, "convex"):
                convex_ok = store.convex.health().get("ok")
                circuit_state = store.convex.circuit_state
            if hasattr(orch.original, "get_runtime_health"):
                llm_runtime = orch.original.get_runtime_health()
        elif orch and hasattr(orch, "get_runtime_health"):
            llm_runtime = orch.get_runtime_health()
        uptime = time.time() - (start_time or time.time())
        llm_configured = int(llm_runtime.get("configured_profiles", 0) or 0)
        return {
            "status": "healthy" if convex_ok is not False else "degraded",
            "service": "SupportOID",
            "version": "v10",
            "uptime_seconds": round(uptime, 1),
            "checks": {
                "auth": {"ok": True, "latency_ms": 0},
                "sessions": {
                    "ok": True,
                    "latency_ms": 0,
                    "detail": f"{auth.active_session_count} active",
                },
                "convex": {
                    "ok": convex_ok is not False,
                    "latency_ms": 0,
                    "circuit": circuit_state,
                },
                "llm": {
                    "ok": llm_configured > 0,
                    "latency_ms": 0,
                    "detail": (
                        f"{llm_configured} configured profile(s); "
                        f"last={llm_runtime.get('last_model_profile', '') or 'none'}"
                    ),
                },
            },
        }

    def get_security_report(self, auth: AuthService) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        security_data = {}
        if orch and hasattr(orch, "get_security_report"):
            security_data = orch.get_security_report()
        return {
            "auth_failures_24h": auth.login_rate_limiter.stats.get("active_limited", 0),
            "rate_limit_hits_24h": security_data.get("rate_limit_blocks_total", 0),
            "active_sessions": auth.active_session_count,
            "total_sessions": len(auth.active_sessions_list),
            "suspicious_ips": security_data.get("suspicious_ips", []),
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        if orch and hasattr(orch, "get_cache_stats"):
            return orch.get_cache_stats()
        return {
            "total_entries": 0,
            "hit_rate": 0,
            "miss_rate": 0,
            "evictions": 0,
            "memory_usage_mb": 0,
        }

    def clear_cache(self) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        if orch and hasattr(orch, "clear_cache"):
            return {"cleared": orch.clear_cache()}
        return {"cleared": 0}

    def get_memory_status(self) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        if orch and hasattr(orch, "get_memory_status"):
            status = orch.get_memory_status()
            return {
                "rss_mb": float(
                    status.get("rss_mb", status.get("process_rss_mb", 0.0)) or 0.0
                ),
                "heap_mb": float(
                    status.get("heap_mb", status.get("used_mb", 0.0)) or 0.0
                ),
                "gc_collections": int(status.get("gc_collections", 0) or 0),
                "optimization_available": bool(
                    status.get("optimization_available", True)
                ),
            }
        return {
            "rss_mb": 0,
            "heap_mb": 0,
            "gc_collections": 0,
            "optimization_available": False,
        }

    def cleanup_memory(self) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        if orch and hasattr(orch, "force_cleanup"):
            return orch.force_cleanup()
        return {"freed_mb": 0}

    def get_sessions_report(self, auth: AuthService) -> Dict[str, Any]:
        return {
            "active": auth.active_session_count,
            "sessions": auth.active_sessions_list,
            "users_bootstrapped": auth.has_users,
        }

    def get_rate_limit_report(self, auth: AuthService) -> Dict[str, Any]:
        return {
            "active_limits": auth.login_rate_limiter.stats,
            "global_enabled": True,
        }

    def get_tier_report(self) -> Dict[str, Any]:
        orch = getattr(self, "orchestrator", None)
        if orch and hasattr(orch, "rate_limiter"):
            rl = orch.rate_limiter
            tiers = {}
            for tier_name in getattr(rl, "_tiers", {}):
                cfg = rl._tiers.get(tier_name, {})
                tiers[tier_name] = {
                    "rate_limit": cfg.get("requests_per_minute", 0),
                    "features": cfg.get("features", []),
                }
            return tiers
        return {
            "free": {"rate_limit": 20, "features": ["chat"]},
            "pro": {"rate_limit": 100, "features": ["chat", "analytics"]},
            "enterprise": {
                "rate_limit": 1000,
                "features": ["chat", "analytics", "admin"],
            },
        }
