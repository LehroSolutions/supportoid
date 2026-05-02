"""
Model Comparison Dashboard — CLI Command
========================================
Usage:
  python -m src.cli models              # Show full dashboard
  python -m src.cli models --summary     # Compact summary
  python -m src.cli models --provider nvidia   # Filter by provider
  python -m src.cli models --compare     # Head-to-head comparison
"""
from pathlib import Path
import sys, time
from typing import Optional

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def format_dashboard(router=None, include_costs: bool = True) -> str:
    """Render full model comparison dashboard as text table."""
    from src.agents.model_router import ModelRouter, DEFAULT_MODELS
    from src.agents.cost_tracker import CostTracker, PRICING

    router = router or ModelRouter()
    data = router.dashboard_data()
    stats = router.get_stats()

    lines = []
    lines.append("=" * 92)
    lines.append("  SupportOID — Model Comparison Dashboard")
    lines.append(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    lines.append("=" * 92)
    lines.append(f"  Models: {data['total_models']}  |  Providers: {', '.join(data['providers'])}")
    lines.append("-" * 92)
    lines.append("")

    # Model cards
    idx = 1
    for name, info in data["models"].items():
        s = stats.get(name, {})
        lines.append(f"  [{idx}] {name}")
        lines.append(f"      Provider:     {info['provider']}")
        lines.append(f"      Model ID:     {info['model_id']}")
        lines.append(f"      Cost Score:   {info['cost_score']}  |  Power Score: {info['power_score']}")
        lines.append(f"      Capabilities: {', '.join(info['capabilities'])}")
        lines.append(f"      Tokens:       {info['max_tokens']:,}")
        lines.append(f"      Rate Limit:   {info['rated_per_rpm']} RPM")
        # Runtime stats
        lines.append(f"      Requests:     {s.get('total_requests', 0)}")
        lines.append(f"      Avg Latency:  {s.get('avg_latency_ms', 0)} ms")
        lines.append(f"      Total Cost:   ${s.get('total_cost', 0):.6f}")
        lines.append(f"      Total Tokens: {s.get('total_tokens', 0):,}")
        lines.append(f"      Success Rate: {s.get('success_rate', 'N/A')}%")
        lines.append("")
        idx += 1

    # Pricing table
    if include_costs:
        lines.append("-" * 92)
        lines.append("  PRICING (per 1M tokens)")
        lines.append("-" * 92)
        lines.append(f"  {'Model':<24} {'Provider':<14} {'Input':>10} {'Output':>10}")
        lines.append(f"  {'-'*24} {'-'*14} {'-'*10} {'-'*10}")
        for model, p in PRICING.items():
            lines.append(f"  {model:<24} {p['provider']:<14} ${p['input']:>9.2f} ${p['output']:>9.2f}")
        lines.append("")

    # Cost tracker summary
    try:
        tracker = CostTracker()
        cost_stats = tracker.get_all_stats()
        if cost_stats['total_conversations'] > 0:
            lines.append("-" * 92)
            lines.append("  COST TRACKING SUMMARY")
            lines.append("-" * 92)
            lines.append(f"  Conversations Tracked: {cost_stats['total_conversations']}")
            lines.append(f"  Total Cost:            ${cost_stats['total_cost_usd']:.8f}")
            lines.append(f"  Total Calls:           {cost_stats['total_calls']}")
            lines.append(f"  Input Tokens:          {cost_stats['total_input_tokens']:,}")
            lines.append(f"  Output Tokens:         {cost_stats['total_output_tokens']:,}")
            if cost_stats['cost_by_model']:
                lines.append("")
                lines.append("  Cost by Model:")
                for model, cost in cost_stats['cost_by_model'].items():
                    lines.append(f"    {model:<24} ${cost:.8f}")
            lines.append("")
    except Exception:
        pass  # cost tracker may not have data yet

    lines.append("═" * 92)
    return "\n".join(lines)


def format_summary(router=None) -> str:
    """Compact summary — one liner per model."""
    from src.agents.model_router import ModelRouter
    router = router or ModelRouter()
    data = router.dashboard_data()
    stats = router.get_stats()

    lines = []
    lines.append(f"\n{'Model':<24} {'Provider':<12} {'Cost':>5} {'Pwr':>4} {'Reqs':>6} {'Latency':>10} {'Cost$':>10} {'Success%':>10}")
    lines.append("-" * 90)
    for name, info in data["models"].items():
        s = stats.get(name, {})
        sr = s.get('success_rate')
        sr_str = f"{sr}%" if sr is not None else "N/A"
        lines.append(
            f"  {name:<24} {info['provider']:<12} {info['cost_score']:>5} "
            f"{info['power_score']:>4} {s.get('total_requests', 0):>6} "
            f"{s.get('avg_latency_ms', 0):>9}ms ${s.get('total_cost', 0):>8.6f} "
            f"{sr_str:>10}")
    lines.append("")
    return "\n".join(lines)


def run_command(args=None) -> str:
    """CLI entry point for models command."""
    import argparse
    parser = argparse.ArgumentParser(description="Model Comparison Dashboard")
    parser.add_argument("--summary", action="store_true", help="Compact summary view")
    parser.add_argument("--provider", type=str, default=None, help="Filter by provider")
    parser.add_argument("--compare", action="store_true", help="Head-to-head comparison")
    parser.add_argument("--no-costs", action="store_true", help="Hide pricing table")

    parsed = parser.parse_args(args)

    from src.agents.model_router import ModelRouter
    from src.agents.response_comparator import ResponseComparator, ModelResponse

    router = ModelRouter()

    if parsed.summary:
        return format_summary(router)

    if parsed.compare:
        # Head-to-head: compare responses across models
        comparator = ResponseComparator()
        # Demo comparison with sample query
        query = "How do I reset my password?"
        demo_responses = [
            ModelResponse(model_name="qwen3.6-free", response="Go to Settings and click Reset Password.", latency_ms=320, token_estimate=45),
            ModelResponse(model_name="claude-sonnet", response="I'd be happy to help you reset your password! Here's a detailed guide:\n\n1. Go to the login page\n2. Click 'Forgot Password'\n3. Enter your email address\n4. Check your inbox for a reset link\n5. Follow the link to create a new password\n\nIf you don't receive the email within a few minutes, please check your spam folder. Is there anything else I can help with?", latency_ms=1200, token_estimate=180),
            ModelResponse(model_name="groq-llama", response="Click 'Forgot Password' on the login page and follow the reset instructions.", latency_ms=150, token_estimate=30),
        ]
        comparison = comparator.compare(demo_responses, query)

        lines = []
        lines.append("=" * 70)
        lines.append("  Head-to-Head Model Comparison")
        lines.append(f"  Query: \"{query}\"")
        lines.append("=" * 70)
        lines.append("")

        for result in comparison["comparison"]:
            lines.append(f"  Model: {result['model_name']}")
            lines.append(f"  Latency: {result['latency_ms']} ms")
            scores = result['scores']
            lines.append(f"  Scores:")
            for cat, score in scores.items():
                bar = "█" * int(score * 10)
                lines.append(f"    {cat:<20} {score:.1f}/1.0 {bar}")
            lines.append("")

        recs = comparison['recommendations']
        lines.append("  RECOMMENDATIONS:")
        lines.append(f"    Best Overall: {recs['best_overall']}")
        lines.append(f"    Fastest:      {recs['fastest']}")
        lines.append("    Winners by category:")
        for cat, winner in recs.get('winners_by_category', {}).items():
            lines.append(f"      {cat}: {winner}")
        lines.append("")
        lines.append("═" * 70)
        return "\n".join(lines)

    return format_dashboard(router, not parsed.no_costs)
