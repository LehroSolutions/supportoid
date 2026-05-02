"""
Automatic Trace Summarization
===============================
Generates concise, readable summaries from raw session traces:
  • One-line executive summary
  • Agent performance breakdown
  • Issue detection (escalations, errors, low-quality responses)
  • Cross-session pattern highlighting
  • Recommended actions

Used by the Trace Viewer UI and multi-session correlation dashboard.
"""

import json
import os
import logging
from typing import Optional

logger = logging.getLogger("supportoid.trace_summary")


def summarize_single_trace(trace: dict) -> dict:
    """Generate a summary for a single session trace."""
    steps = trace.get("steps", [])
    session_id = trace.get("session_id", "unknown")
    duration = trace.get("duration_s", trace.get("duration", 0))
    error = trace.get("error")

    # Count agent actions
    agent_counts = {}
    agent_times = {}
    for step in steps:
        agent = step.get("agent", "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1
        dur = step.get("duration_ms", 0)
        agent_times[agent] = agent_times.get(agent, 0) + dur

    # Find slowest agent
    slowest = max(agent_times.items(), key=lambda x: x[1]) if agent_times else ("none", 0)

    # Detect escalation
    escalated = any("escalat" in step.get("action", "").lower() or
                    "handoff" in step.get("action", "").lower()
                    for step in steps)

    # Detect quality warnings
    quality_warnings = [s for s in steps if s.get("status") == "warning"]

    # Model used
    model = trace.get("model", "unknown")
    cost = trace.get("cost")
    tokens = trace.get("tokens")

    # Generate one-line summary
    user_input = trace.get("user_input", "")
    input_preview = user_input[:60] + "..." if len(user_input) > 60 else user_input

    if escalated:
        summary = f"⚡ Escalated to human — {input_preview}"
    elif error:
        summary = f"❌ Error ({error}) — {input_preview}"
    elif quality_warnings:
        reasons = ", ".join(s.get("reason", "quality issue") for s in quality_warnings[:2])
        summary = f"⚠ Quality warning: {reasons} — {input_preview}"
    else:
        total_steps = len(steps)
        summary = f"✅ Resolved in {total_steps} steps ({duration:.03f}s) — {input_preview}"

    return {
        "session_id": session_id,
        "summary": summary,
        "duration_s": round(duration, 3),
        "total_steps": len(steps),
        "agent_breakdown": agent_counts,
        "slowest_agent": {"name": slowest[0], "total_ms": slowest[1]},
        "escalated": escalated,
        "has_error": bool(error),
        "has_warnings": len(quality_warnings) > 0,
        "warning_details": [{"agent": s.get("agent"), "reason": s.get("reason")} for s in quality_warnings],
        "model": model,
        "cost": cost,
        "tokens": tokens,
    }


def summarize_multiple_traces(traces: list[dict]) -> dict:
    """Generate a cross-session summary report."""
    if not traces:
        return {"total_sessions": 0}

    summaries = [summarize_single_trace(t) for t in traces]

    total = len(summaries)
    escalated = sum(1 for s in summaries if s["escalated"])
    errors = sum(1 for s in summaries if s["has_error"])
    warnings = sum(1 for s in summaries if s["has_warnings"])
    healthy = total - escalated - errors - warnings

    # Avg stats
    durations = [s["duration_s"] for s in summaries]
    avg_duration = sum(durations) / total if durations else 0
    total_steps = sum(s["total_steps"] for s in summaries)

    # Agent workload
    agent_totals = {}
    for s in summaries:
        for agent, count in s["agent_breakdown"].items():
            agent_totals[agent] = agent_totals.get(agent, 0) + count

    # Model distribution
    model_counts = {}
    for s in summaries:
        m = s.get("model", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1

    # Slowest sessions
    slowest_sessions = sorted(summaries, key=lambda x: x["duration_s"], reverse=True)[:5]

    # Cost summary
    total_cost = sum(s.get("cost", 0) or 0 for s in summaries)
    total_tokens = sum(s.get("tokens", 0) or 0 for s in summaries)

    return {
        "total_sessions": total,
        "healthy_rate": round(healthy / total * 100, 1) if total else 0,
        "escalations": escalated,
        "errors": errors,
        "warnings": warnings,
        "avg_duration_s": round(avg_duration, 3),
        "total_steps": total_steps,
        "agent_workload": dict(sorted(agent_totals.items(), key=lambda x: x[1], reverse=True)),
        "model_distribution": model_counts,
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "slowest_sessions": [{"session_id": s["session_id"], "duration_s": s["duration_s"], "summary": s["summary"]}
                             for s in slowest_sessions],
        "executive_summary": _executive_summary(total, healthy, escalated, errors, avg_duration),
        "session_summaries": summaries,
    }


def _executive_summary(total, healthy, escalated, errors, avg_dur) -> str:
    """Generate a human-readable executive summary."""
    health_pct = round(healthy / max(total, 1) * 100, 1)

    if health_pct >= 90:
        overall = "Excellent"
    elif health_pct >= 70:
        overall = "Good"
    elif health_pct >= 50:
        overall = "Needs Attention"
    else:
        overall = "Critical"

    parts = [f"📊 Overall Health: {overall} ({health_pct}%)"]
    if escalated:
        parts.append(f"⚡ {escalated} escalation(s) to human agents")
    if errors:
        parts.append(f"❌ {errors} session(s) with errors")
    parts.append(f"⏱ Avg response: {avg_dur:.3f}s")
    parts.append(f"📦 {total} sessions processed")

    return " | ".join(parts)


def generate_trace_summary_file(traces_dir: str, output_path: str = None) -> str:
    """Load all traces from directory and write summary report."""
    traces = []
    if os.path.isdir(traces_dir):
        for fn in os.listdir(traces_dir):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(traces_dir, fn)) as f:
                        traces.append(json.load(f))
                except Exception:
                    pass

    report = summarize_multiple_traces(traces)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    return report
