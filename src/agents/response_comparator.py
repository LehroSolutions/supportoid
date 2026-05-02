"""
Multi-Model Response Comparator
====================================
Compare responses from multiple AI models for the same task.
From multi-model-response-comparator skill.

Use cases:
  • Benchmark prompts across models
  • Choose best model for a workflow
  • Generate second opinions on critical decisions
"""

import time, asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class ModelResponse:
    model_name: str
    response: str
    latency_ms: float
    token_estimate: int
    rubric_scores: Dict[str, float] = field(default_factory=dict)


class ResponseComparator:
    """Compare responses from multiple models using a structured rubric."""

    DEFAULT_RUBRIC = {
        "correctness": "Is the information accurate and complete?",
        "depth": "How thorough is the analysis?",
        "clarity": "How easy is it to understand?",
        "actionability": "Can the user act on this immediately?",
        "empathy": "Does it acknowledge the user's situation?",
        "safety": "Are there any risky or unsafe suggestions?",
    }

    def __init__(self, models: List[str] = None):
        self.models = models or ["qwen3.6-free", "claude-sonnet", "groq-llama"]

    def score_response(self, response: str, query: str, rubric: Dict[str, str] = None) -> Dict[str, float]:
        """Score a response using keyword-based heuristics per rubric category."""
        scores = {}
        r = rubric or self.DEFAULT_RUBRIC
        text = response.lower()
        length = len(response.split())

        for category in r:
            score = 0.5  # baseline

            if category == "correctness":
                if length > 30: score += 0.2
                if any(w in text for w in ["specific", "according", "based on", "this means"]): score += 0.1
                if any(w in text for w in ["i don't know", "i'm not sure", "i cannot"]): score += 0.1  # Honesty
                if "guarantee" in text and "money-back" not in text: score -= 0.2

            elif category == "depth":
                if length > 100: score += 0.2
                if "\n" in text: score += 0.1
                if text.count("•") + text.count("-") + text.count("1.") > 3: score += 0.15
                if any(section in text for section in ["here are", "here's", "steps:", "follow these"]): score += 0.1

            elif category == "clarity":
                if length > 150: score -= 0.1  # Too long
                if any(w in text for w in ["in short", "to summarize", "basically"]): score += 0.1
                if text.count(".") / max(length, 1) > 0.03: score += 0.1  # Good sentence structure

            elif category == "actionability":
                if any(w in text for w in ["go to", "click", "navigate", "select", "try", "check"]): score += 0.2
                if text.count("1.") + text.count("2.") + text.count("3.") >= 2: score += 0.15
                if any(w in text for w in ["first", "second", "next", "finally"]): score += 0.1

            elif category == "empathy":
                if any(w in text for w in ["understand", "sorry", "frustrating", "apologize", "hear you"]): score += 0.25
                if any(w in text for w in ["i can", "i'll", "let me"]): score += 0.1
                if "😊" in response or "😄" in response: score -= 0.1  # Inappropriate for support

            elif category == "safety":
                score = 1.0  # Start high, deduct for issues
                if any(w in text for w in ["guaranteed", "100%", "definitely", "always", "never"]): score -= 0.2
                if any(w in text for w in ["your fault", "you should have", "blame"]): score -= 0.3
                if any(w in text for w in ["policy says", "can't help"]): score -= 0.15

            scores[category] = round(max(0, min(1, score)), 3)

        scores["overall"] = round(sum(scores.values()) / len(scores), 3)
        return scores

    def compare(self, responses: List[ModelResponse], query: str,
               rubric: Dict[str, str] = None) -> Dict:
        """Compare multiple model responses and produce a structured summary."""
        results = []
        for resp in responses:
            scores = self.score_response(resp.response, query, rubric)
            results.append({
                "model_name": resp.model_name,
                "scores": scores,
                "latency_ms": resp.latency_ms,
            })

        # Find winners per category
        winners = {}
        for cat in (rubric or self.DEFAULT_RUBRIC).keys():
            if cat == "overall": continue
            best = max(results, key=lambda x: x["scores"].get(cat, 0))
            winners[cat] = best["model_name"]

        # Overall winner
        overall = max(results, key=lambda x: x["scores"].get("overall", 0))

        # Recommendations
        recommendations = {
            "best_overall": overall["model_name"],
            "fastest": min(results, key=lambda x: x["latency_ms"])["model_name"],
            "winners_by_category": winners,
        }

        return {
            "comparison": results,
            "recommendations": recommendations,
            "query": query,
            "models_compared": len(results),
        }
