"""
Conversation Cost Tracker
=========================
Per-conversation cost tracking across all model providers.
Tracks:
  • Token usage (input / output / total)
  • Cost per provider (based on published rates)
  • Latency per call
  • Accumulated conversation cost
"""
import time, json, threading
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field


# Published rates per 1M tokens (USD) — approximate as of 2026-04
PRICING = {
    "gpt-oss-remote":     {"input": 0.0,  "output": 0.0,  "provider": "openai-compatible"},
    "gemma4-remote":      {"input": 0.0,  "output": 0.0,  "provider": "openai-compatible"},
    "gpt-oss-local":      {"input": 0.0,  "output": 0.0,  "provider": "openai-compatible"},
    "gemma4-local":       {"input": 0.0,  "output": 0.0,  "provider": "openai-compatible"},
    "qwen3.6-free":       {"input": 0.0,  "output": 0.0,  "provider": "openrouter"},
    "claude-sonnet":      {"input": 3.0,  "output": 15.0, "provider": "anthropic"},
    "gpt-4o-mini":        {"input": 0.15, "output": 0.60, "provider": "openai"},
    "groq-llama":         {"input": 0.59, "output": 0.79, "provider": "groq"},
    "gemini-pro":         {"input": 0.075,"output": 0.30, "provider": "google"},
    "deepseek-v3":        {"input": 0.14, "output": 0.28, "provider": "deepseek"},
    "nvidia-personaplex": {"input": 0.05, "output": 0.10, "provider": "nvidia"},
}


@dataclass
class ModelCall:
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: float
    timestamp: float


@dataclass
class ConversationCost:
    conversation_id: str
    calls: List[ModelCall] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    models_used: Dict[str, int] = field(default_factory=dict)

    def add_call(self, model: str, input_tokens: int, output_tokens: int,
                 latency_ms: float) -> float:
        pricing = PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = ((input_tokens * pricing["input"]) + (output_tokens * pricing["output"])) / 1_000_000
        call = ModelCall(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cost=round(cost, 8), latency_ms=latency_ms, timestamp=time.time(),
        )
        self.calls.append(call)
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.total_latency_ms += latency_ms
        self.models_used[model] = self.models_used.get(model, 0) + 1
        return call.cost


class CostTracker:
    """Thread-safe per-conversation cost tracking with persistence."""

    def __init__(self, data_dir: str = "./data/costs"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conversations: Dict[str, ConversationCost] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        for f in self.data_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                cc = ConversationCost(conversation_id=data["conversation_id"])
                cc.total_input_tokens = data.get("total_input_tokens", 0)
                cc.total_output_tokens = data.get("total_output_tokens", 0)
                cc.total_cost = data.get("total_cost", 0.0)
                cc.total_latency_ms = data.get("total_latency_ms", 0.0)
                cc.models_used = data.get("models_used", {})
                cc.calls = [
                    ModelCall(**c) for c in data.get("calls", [])
                    if isinstance(c, dict)
                ]
                self.conversations[data["conversation_id"]] = cc
            except Exception:
                pass

    def record(self, conversation_id: str, model: str, input_tokens: int,
               output_tokens: int, latency_ms: float) -> Dict:
        """Record a model call and per-remaining cost info."""
        with self._lock:
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = ConversationCost(
                    conversation_id=conversation_id)
            cc = self.conversations[conversation_id]
            call_cost = cc.add_call(model, input_tokens, output_tokens, latency_ms)
            return {
                "call_cost_usd": round(call_cost, 8),
                "conversation_total_usd": round(cc.total_cost, 8),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": round(latency_ms, 1),
            }

    def get_conversation(self, conversation_id: str) -> Optional[Dict]:
        cc = self.conversations.get(conversation_id)
        if not cc:
            return None
        return {
            "conversation_id": cc.conversation_id,
            "total_cost_usd": round(cc.total_cost, 8),
            "total_input_tokens": cc.total_input_tokens,
            "total_output_tokens": cc.total_output_tokens,
            "total_latency_ms": round(cc.total_latency_ms, 1),
            "models_used": cc.models_used,
            "call_count": len(cc.calls),
        }

    def save_conversation(self, conversation_id: str):
        cc = self.conversations.get(conversation_id)
        if not cc:
            return
        with self._lock:
            data = {
                "conversation_id": cc.conversation_id,
                "total_input_tokens": cc.total_input_tokens,
                "total_output_tokens": cc.total_output_tokens,
                "total_cost": round(cc.total_cost, 8),
                "total_latency_ms": round(cc.total_latency_ms, 2),
                "models_used": cc.models_used,
                "calls": [
                    {
                        "model": c.model, "input_tokens": c.input_tokens,
                        "output_tokens": c.output_tokens, "cost": c.cost,
                        "latency_ms": c.latency_ms, "timestamp": c.timestamp,
                    }
                    for c in cc.calls
                ],
            }
            with open(self.data_dir / f"{conversation_id}.json", "w") as f:
                json.dump(data, f, indent=2)

    def get_all_stats(self) -> Dict:
        totals = {
            "total_conversations": len(self.conversations),
            "total_cost_usd": 0.0,
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "cost_by_model": {},
            "calls_by_model": {},
        }
        for cc in self.conversations.values():
            totals["total_cost_usd"] += cc.total_cost
            totals["total_calls"] += len(cc.calls)
            totals["total_input_tokens"] += cc.total_input_tokens
            totals["total_output_tokens"] += cc.total_output_tokens
            for model, count in cc.models_used.items():
                totals["calls_by_model"][model] = (
                    totals["calls_by_model"].get(model, 0) + count)
        totals["total_cost_usd"] = round(totals["total_cost_usd"], 8)
        # Compute cost by model from individual calls
        for cc in self.conversations.values():
            for call in cc.calls:
                totals["cost_by_model"][call.model] = round(
                    totals["cost_by_model"].get(call.model, 0) + call.cost, 8)
        return totals

    def get_pricing_table(self) -> List[Dict]:
        """Return pricing info for all known model providers."""
        rows = []
        for model, p in PRICING.items():
            rows.append({
                "model": model,
                "provider": p["provider"],
                "input_per_1M": f"${p['input']:.2f}",
                "output_per_1M": f"${p['output']:.2f}",
            })
        return rows
