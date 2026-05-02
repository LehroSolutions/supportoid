"""
Cost Tracking CLI Command
=========================
Usage:
  python -m src.cli costs                # Show cost summary
  python -m src.cli costs --conversation conv_123  # Per-conversation cost
  python -m src.cli costs --pricing      # Pricing table
"""
from pathlib import Path
import sys, json
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def run_command(args=None) -> str:
    import argparse
    parser = argparse.ArgumentParser(description="Cost Tracking")
    parser.add_argument("--conversation", type=str, help="Specific conversation ID")
    parser.add_argument("--pricing", action="store_true", help="Show pricing table")
    parser.add_argument("--export", action="store_true", help="Export as JSON")
    parsed = parser.parse_args(args)

    from src.agents.cost_tracker import CostTracker, PRICING

    if parsed.export:
        tracker = CostTracker()
        stats = tracker.get_all_stats()
        return json.dumps(stats, indent=2)

    lines = []

    if parsed.pricing:
        lines.append("=" * 60)
        lines.append("  SupportOID — Pricing Table (per 1M tokens)")
        lines.append("=" * 60)
        lines.append(f"  {'Model':<24} {'Provider':<14} {'Input':>10} {'Output':>10}")
        lines.append(f"  {'-'*24} {'-'*14} {'-'*10} {'-'*10}")
        for model, p in PRICING.items():
            lines.append(f"  {model:<24} {p['provider']:<14} ${p['input']:>9.2f} ${p['output']:>9.2f}")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    if parsed.conversation:
        tracker = CostTracker()
        convo = tracker.get_conversation(parsed.conversation)
        if convo:
            lines.append(f"Conversation: {convo['conversation_id']}")
            lines.append(f"  Total Cost:      ${convo['total_cost_usd']:.8f}")
            lines.append(f"  Input Tokens:    {convo['total_input_tokens']:,}")
            lines.append(f"  Output Tokens:   {convo['total_output_tokens']:,}")
            lines.append(f"  Latency:         {convo['total_latency_ms']} ms")
            lines.append(f"  Models Used:     {convo['models_used']}")
            lines.append(f"  Number of Calls: {convo['call_count']}")
        else:
            lines.append(f"No cost data found for conversation: {parsed.conversation}")
        return "\n".join(lines)

    # Default: overall summary
    tracker = CostTracker()
    stats = tracker.get_all_stats()
    lines.append("=" * 60)
    lines.append("  SupportOID — Cost Tracking Summary")
    lines.append("=" * 60)
    lines.append(f"  Conversations:      {stats['total_conversations']}")
    lines.append(f"  Total Cost:         ${stats['total_cost_usd']:.8f}")
    lines.append(f"  Total API Calls:    {stats['total_calls']}")
    lines.append(f"  Input Tokens:       {stats['total_input_tokens']:,}")
    lines.append(f"  Output Tokens:      {stats['total_output_tokens']:,}")
    if stats['cost_by_model']:
        lines.append("")
        lines.append("  Cost by Model:")
        for model, cost in stats['cost_by_model'].items():
            lines.append(f"    {model:<24} ${cost:.8f}")
    if stats['calls_by_model']:
        lines.append("")
        lines.append("  Calls by Model:")
        for model, count in stats['calls_by_model'].items():
            lines.append(f"    {model:<24} {count} calls")
    if not stats['cost_by_model'] and not stats['calls_by_model']:
        lines.append("")
        lines.append("  No usage data recorded yet. Costs are tracked per conversation.")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
