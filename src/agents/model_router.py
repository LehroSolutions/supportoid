"""
Multi-Model Router v2 — NVIDIA PersonaPlex + Fallback Chain
===========================================================
Routes requests to the optimal AI model based on:
  • Task complexity (short/simple → cheap, long/complex → powerful)
  • Cost scores per model
  • Required capabilities (chat, code, analysis, speed, voice)
  • User preferences, latency requirements
  • NVIDIA PersonaPlex as a first-class provider
  • Multi-model fallback chain for resilience
"""

import json, os, time, re
from typing import List, Dict, Optional
from dataclasses import dataclass

# Default model configurations — includes NVIDIA PersonaPlex
DEFAULT_MODELS: list[dict] = [
    {
        "name": "qwen3.6-free",
        "provider": "openrouter",
        "model_id": "qwen/qwen3.6-plus-preview:free",
        "cost_score": 1,
        "power_score": 85,
        "capabilities": ["chat", "code", "general"],
        "max_tokens": 32000,
        "rate_limit_rpm": 100,
        "priority": 3,
    },
    {
        "name": "claude-sonnet",
        "provider": "anthropic",
        "model_id": "claude-3-5-sonnet-20241022",
        "cost_score": 15,
        "power_score": 92,
        "capabilities": ["chat", "code", "analysis", "security"],
        "max_tokens": 200000,
        "rate_limit_rpm": 200,
        "priority": 1,
    },
    {
        "name": "gpt-4o-mini",
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "cost_score": 5,
        "power_score": 85,
        "capabilities": ["chat", "code", "tools", "vision"],
        "max_tokens": 128000,
        "rate_limit_rpm": 500,
        "priority": 3,
    },
    {
        "name": "groq-llama",
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "cost_score": 3,
        "power_score": 80,
        "capabilities": ["chat", "code", "speed"],
        "max_tokens": 128000,
        "rate_limit_rpm": 1000,
        "priority": 3,
    },
    {
        "name": "gemini-pro",
        "provider": "google",
        "model_id": "gemini-2.0-flash",
        "cost_score": 8,
        "power_score": 88,
        "capabilities": ["chat", "code", "analysis", "long-context"],
        "max_tokens": 1000000,
        "rate_limit_rpm": 300,
        "priority": 2,
    },
    {
        "name": "deepseek-v3",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "cost_score": 2,
        "power_score": 85,
        "capabilities": ["chat", "code", "math"],
        "max_tokens": 64000,
        "rate_limit_rpm": 200,
        "priority": 3,
    },
    {
        "name": "nvidia-personaplex",
        "provider": "nvidia",
        "model_id": "nvidia/personaplex-7b-v1",
        "cost_score": 4,
        "power_score": 87,
        "capabilities": ["chat", "code", "voice", "persona", "conversational"],
        "max_tokens": 4096,
        "rate_limit_rpm": 120,
        "priority": 2,
    },
]

COMPLEX_KEYWORDS = [
    "design", "analysis", "explain", "compare", "translate", "optimize",
    "refactor", "bug", "debug", "legal", "medical", "code", "implement",
    "security", "accuracy", "architecture", "algorithm", "performance",
    "complex", "enterprise", "compliance", "audit", "investigate"
]

SIMPLE_KEYWORDS = [
    "hi", "hello", "help", "thanks", "ok", "yes", "no", "what",
    "when", "where", "who", "how much", "hours", "reset", "password"
]

VOICE_KEYWORDS = [
    "call", "phone", "speak", "talk", "voice", "hear", "call me",
    "speak to", "on the phone", "verbal", "spoken",
]


@dataclass
class ModelSelection:
    model_name: str
    model_id: str
    provider: str
    reason: str
    complexity_score: int
    estimated_cost: float
    estimated_latency_ms: float
    fallback_chain: list = None
    voice_capable: bool = False


class FallbackChain:
    """Manages ordered fallback chain for model resilience."""

    def __init__(self, primary: str, all_models: list[dict]):
        model_map = {m["name"]: m for m in all_models}
        primary_model = model_map.get(primary, {})
        primary_caps = set(primary_model.get("capabilities", []))

        fallbacks = []
        for m in all_models:
            if m["name"] == primary:
                continue
            # Include ALL models as fallbacks, rank by capability overlap + cost
            caps = set(m["capabilities"])
            overlap = len(primary_caps & caps)
            score = (overlap * 10) - m["cost_score"] + (m.get("priority", 3) * 2)
            fallbacks.append((score, m["cost_score"], m.get("priority", 9), m["name"]))

        fallbacks.sort()
        self._chain = [primary] + [f[3] for f in fallbacks]

    def chain(self) -> list[str]:
        return list(self._chain)

    def next_after(self, failed_model: str) -> Optional[str]:
        try:
            idx = self._chain.index(failed_model)
            return self._chain[idx + 1] if idx + 1 < len(self._chain) else self._chain[0]
        except (ValueError, IndexError):
            return self._chain[0] if self._chain else None


class ModelRouter:
    """Routes requests to the optimal AI model with fallback chain."""

    def __init__(self, models: list[dict] = None, config_path: str = None):
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                self.models = json.load(f)
        else:
            self.models = models or DEFAULT_MODELS

        self.rate_limits = {
            m["name"]: {"count": 0, "window_start": time.monotonic()} for m in self.models
        }
        self.usage_stats = {
            m["name"]: {
                "total_requests": 0, "total_cost": 0, "total_latency_ms": 0,
                "total_failures": 0, "total_tokens": 0,
            }
            for m in self.models
        }
        self._recent_failures = {m["name"]: [] for m in self.models}

    def score_complexity(self, text: str) -> int:
        """Score text complexity 0-10."""
        if not text:
            return 0
        t = text.lower()
        score = 0

        if len(t) > 500:
            score += 3
        elif len(t) > 200:
            score += 2
        elif len(t) > 80:
            score += 1

        for kw in COMPLEX_KEYWORDS:
            if kw in t:
                score += 1

        for kw in SIMPLE_KEYWORDS:
            if kw in t:
                score = max(0, score - 1)

        if t.count("?") > 2:
            score += 1
        if re.search(r'(?:how|what|why|when|where)\s+do\s+(?:i|we|you)\s+', t):
            score += 1
        if re.search(r'\.[a-z]{2,}\(', t):
            score += 1
        if re.search(r'(?i)(?:api|http|endpoint|schema|database|server)', t):
            score += 1

        return min(10, score)

    def _is_voice_request(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in VOICE_KEYWORDS)

    def select(self, text: str, required_capabilities: list[str] = None,
               max_cost_score: float = None, max_latency_ms: float = None,
               prefer_voice: bool = False) -> ModelSelection:
        complexity = self.score_complexity(text)
        required_caps = set(required_capabilities or []) if required_capabilities else set()

        is_voice = prefer_voice or self._is_voice_request(text)
        if is_voice:
            required_caps.add("voice")

        candidates = []
        for m in self.models:
            caps = set(m["capabilities"])
            if required_caps and not required_caps.issubset(caps):
                continue

            now = time.monotonic()
            rl = self.rate_limits[m["name"]]
            if now - rl["window_start"] > 60:
                rl["count"] = 0
                rl["window_start"] = now
            if rl["count"] >= m["rate_limit_rpm"]:
                continue

            failures_60s = [f for f in self._recent_failures[m["name"]]
                           if time.monotonic() - f < 60]
            self._recent_failures[m["name"]] = failures_60s
            if len(failures_60s) >= 3:
                continue

            if max_cost_score and m["cost_score"] > max_cost_score:
                continue

            candidates.append(m)

        if not candidates:
            candidates = sorted(self.models, key=lambda x: x["cost_score"])

        if complexity <= 2:
            best = min(candidates, key=lambda x: x["cost_score"])
            reason = f"simple (complexity={complexity}) -> cheapest"
        elif complexity <= 5:
            best = min(candidates, key=lambda x: x["cost_score"] - x["power_score"] * 0.1)
            reason = f"medium (complexity={complexity}) -> cost-quality balance"
        elif complexity <= 7:
            best = max(candidates, key=lambda x: x["power_score"] - x["cost_score"] * 0.05)
            reason = f"complex (complexity={complexity}) -> quality"
        else:
            best = max(candidates, key=lambda x: x["power_score"])
            reason = f"very complex (complexity={complexity}) -> most powerful"

        if is_voice:
            reason += " [voice-enabled]"

        text_len = len(text) if text else 100
        estimated_cost = best["cost_score"] * (text_len / 1000) * 0.001
        estimated_latency = 500 if "speed" in best["capabilities"] else 800
        if complexity > 6:
            estimated_latency *= 1.5

        fc = FallbackChain(best["name"], self.models)
        voice_capable = "voice" in set(best.get("capabilities", []))

        return ModelSelection(
            model_name=best["name"],
            model_id=best["model_id"],
            provider=best["provider"],
            reason=reason,
            complexity_score=complexity,
            estimated_cost=round(estimated_cost, 6),
            estimated_latency_ms=estimated_latency,
            fallback_chain=fc.chain(),
            voice_capable=voice_capable,
        )

    def record_failure(self, model_name: str):
        """Record a model call failure for fallback tracking."""
        if model_name in self._recent_failures:
            self._recent_failures[model_name].append(time.monotonic())
        if model_name in self.usage_stats:
            self.usage_stats[model_name]["total_failures"] += 1

    def record_usage(self, model_name: str, latency_ms: float, cost: float,
                     tokens: int = 0):
        """Record actual usage stats."""
        if model_name in self.usage_stats:
            s = self.usage_stats[model_name]
            s["total_requests"] += 1
            s["total_latency_ms"] += latency_ms
            s["total_cost"] += cost
            s["total_tokens"] += tokens
        if model_name in self.rate_limits:
            self.rate_limits[model_name]["count"] += 1
            self._recent_failures[model_name] = []

    def get_stats(self) -> Dict:
        stats = {}
        for name, usage in self.usage_stats.items():
            reqs = usage["total_requests"]
            total_attempts = reqs + usage.get("total_failures", 0)
            stats[name] = {
                "total_requests": reqs,
                "avg_latency_ms": round(usage["total_latency_ms"] / reqs, 1) if reqs else 0,
                "total_cost": round(usage["total_cost"], 6),
                "total_tokens": usage.get("total_tokens", 0),
                "total_failures": usage.get("total_failures", 0),
                "success_rate": round(reqs / max(total_attempts, 1) * 100, 1) if total_attempts else None,
            }
        return stats

    def available_models(self) -> list[dict]:
        return list(self.models)

    def dashboard_data(self) -> dict:
        """Generate data for the CLI model comparison dashboard."""
        stats = self.get_stats()
        model_info = {}
        for m in self.models:
            s = stats.get(m["name"], {})
            model_info[m["name"]] = {
                "provider": m["provider"],
                "model_id": m["model_id"],
                "cost_score": m["cost_score"],
                "power_score": m["power_score"],
                "capabilities": m["capabilities"],
                "max_tokens": m["max_tokens"],
                "rated_per_rpm": m["rate_limit_rpm"],
                "total_requests": s.get("total_requests", 0),
                "avg_latency_ms": s.get("avg_latency_ms", 0),
                "total_cost": s.get("total_cost", 0),
                "total_tokens": s.get("total_tokens", 0),
                "success_rate": s.get("success_rate"),
            }
        return {
            "models": model_info,
            "total_models": len(self.models),
            "providers": sorted(set(m["provider"] for m in self.models)),
        }
