"""
Knowledge Base Quality Scoring
===============================
Comprehensive quality assessment for KB entries:
  • Content completeness scoring
  • Freshness / staleness detection
  • Usage effectiveness (from feedback)
  • Clarity & readability metrics
  • Coverage gap analysis
  • Overall quality dashboard data
"""

import json
import os
import re
import math
import logging
from datetime import datetime, timezone
from typing import Optional

from src.app.timeutils import utc_now, utc_now_iso

logger = logging.getLogger("supportoid.kb_quality")


class KBQualityScorer:
    """Scores and monitors knowledge base entry quality."""

    def __init__(self, kb_dir: str, feedback_dir: str = None):
        self.kb_dir = kb_dir
        self.feedback_dir = feedback_dir
        self.entries: dict = {}
        self._load_kb()

    def _load_kb(self):
        if not os.path.isdir(self.kb_dir):
            return
        for fn in os.listdir(self.kb_dir):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(self.kb_dir, fn)) as f:
                        e = json.load(f)
                    self.entries[e["id"]] = e
                except Exception:
                    pass

    def score_single(self, entry: dict) -> dict:
        """Score a single KB entry across all quality dimensions."""
        scores = {
            "completeness": self._score_completeness(entry),
            "clarity": self._score_clarity(entry),
            "freshness": self._score_freshness(entry),
            "usage_effectiveness": self._score_usage(entry),
            "coverage": self._score_coverage(entry),
        }
        weights = {
            "completeness": 0.25,
            "clarity": 0.20,
            "freshness": 0.15,
            "usage_effectiveness": 0.25,
            "coverage": 0.15,
        }
        overall = sum(scores[k] * weights[k] for k in weights)
        return {
            "entry_id": entry["id"],
            "title": entry.get("title", ""),
            "dimensions": scores,
            "weights": weights,
            "overall": round(overall, 3),
            "grade": self._grade(overall),
            "recommendations": self._recommendations(scores, entry),
        }

    def score_all(self) -> dict:
        """Score all KB entries and provide aggregate report."""
        individual = {}
        for eid, entry in self.entries.items():
            individual[eid] = self.score_single(entry)

        if not individual:
            return {"total_entries": 0, "overall_avg": 0, "entries": {}}

        all_scores = [v["overall"] for v in individual.values()]
        avg = sum(all_scores) / len(all_scores)

        # Grade distribution
        grades = Counter(v["grade"] for v in individual.values())

        # Top / bottom entries
        sorted_entries = sorted(individual.items(), key=lambda x: x[1]["overall"])
        bottom_3 = {k: v for k, v in sorted_entries[:3]}
        top_3 = {k: v for k, v in reversed(sorted_entries[-3:])}

        # Dimension averages
        dims = ["completeness", "clarity", "freshness", "usage_effectiveness", "coverage"]
        dim_avgs = {d: round(sum(v["dimensions"][d] for v in individual.values()) / len(individual), 3)
                    for d in dims}

        return {
            "total_entries": len(individual),
            "overall_avg": round(avg, 3),
            "grade_distribution": dict(grades),
            "dimension_averages": dim_avgs,
            "top_entries": top_3,
            "needs_attention": bottom_3,
            "entries": individual,
            "report_generated": utc_now_iso(),
        }

    def find_coverage_gaps(self, known_intents: list[str] = None) -> list[dict]:
        """Identify intents or topics with insufficient KB coverage."""
        if not known_intents:
            known_intents = [
                "account_management", "billing_inquiry", "refund_request",
                "product_inquiry", "technical_issue", "onboarding_help",
                "complaint", "feature_request", "cancellation",
                "order_tracking", "shipping_question", "general",
            ]

        intent_coverage = {}
        for intent in known_intents:
            matching = [e for e in self.entries.values() if e.get("intent") == intent]
            total_quality = sum(e.get("quality", 0.5) for e in matching) if matching else 0
            intent_coverage[intent] = {
                "entry_count": len(matching),
                "total_quality": round(total_quality, 2),
                "has_coverage": len(matching) > 0,
                "quality_level": "good" if total_quality >= 2.0 else ("partial" if matching else "none"),
            }

        gaps = [
            {"intent": intent, **data}
            for intent, data in intent_coverage.items()
            if not data["has_coverage"] or data["quality_level"] == "none"
        ]
        return gaps

    # ── Individual scoring methods ──

    def _score_completeness(self, entry: dict) -> float:
        """How complete is the content? Based on length, structure, actionability."""
        content = entry.get("content", "")
        title = entry.get("title", "")
        score = 0.0

        # Title quality
        if len(title) > 5:
            score += 0.1
        if len(title) > 20:
            score += 0.05

        # Content length — reasonable minimum
        word_count = len(content.split())
        if word_count >= 10:
            score += 0.2
        if word_count >= 30:
            score += 0.15
        if word_count >= 50:
            score += 0.1

        # Has structure (numbered steps, bullet points)
        if re.search(r'\d+\.', content):
            score += 0.15  # Numbered steps
        if re.search(r'•|[-*]\s', content):
            score += 0.1  # Bullet points
        if '\n' in content:
            score += 0.05  # Multi-line

        # Has actionable language
        action_words = ['go to', 'click', 'enter', 'select', 'check', 'open', 'visit', 'use', 'set']
        cl = content.lower()
        if any(w in cl for w in action_words):
            score += 0.15

        # Tags present
        if entry.get("tags"):
            score += 0.1

        return min(1.0, score)

    def _score_clarity(self, entry: dict) -> float:
        """Readability and clarity of the content."""
        content = entry.get("content", "")
        if not content:
            return 0.0

        score = 0.5  # Base score

        # Sentence length — shorter is generally clearer
        sentences = re.split(r'[.!?\n]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        if sentences:
            avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
            if avg_len < 15:
                score += 0.2
            elif avg_len < 25:
                score += 0.1

        # No excessive jargon (simplified check)
        jargon_words = ['utilize', 'implement', 'facilitate', 'leveraging', 'synergy']
        if not any(j in content.lower() for j in jargon_words):
            score += 0.1

        # Clear language (uses direct instructions)
        if any(w in content.lower() for w in ['go to', 'click', 'select', 'enter', 'press']):
            score += 0.1

        return min(1.0, score)

    def _score_freshness(self, entry: dict) -> float:
        """How recently has this entry been updated or used effectively?"""
        # Check for last_updated timestamp
        updated = entry.get("last_updated")
        if updated:
            try:
                updated_at = datetime.fromisoformat(updated)
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                age_days = (utc_now() - updated_at).days
                if age_days < 30:
                    return 1.0
                elif age_days < 90:
                    return 0.8
                elif age_days < 180:
                    return 0.5
                else:
                    return 0.3
            except Exception:
                pass

        # Fallback: usage-based freshness
        usage = entry.get("usage", 0)
        quality = entry.get("quality", 0.5)
        if usage > 10 and quality > 0.8:
            return 0.9  # Frequently used and well-rated
        elif usage > 5 and quality > 0.6:
            return 0.7
        elif usage > 0:
            return 0.5

        return 0.4  # Unknown freshness

    def _score_usage(self, entry: dict) -> float:
        """Effectiveness based on actual usage and feedback."""
        quality = entry.get("quality", 0.5)
        usage = entry.get("usage", 0)

        # Quality weight
        score = quality * 0.7

        # Usage weight (log scale to avoid punishing new entries)
        usage_score = min(1.0, math.log1p(usage) / math.log1p(20))
        score += usage_score * 0.3

        return min(1.0, score)

    def _score_coverage(self, entry: dict) -> float:
        """Does this entry cover its intent well?"""
        content = entry.get("content", "")
        tags = entry.get("tags", [])
        intent = entry.get("intent", "")

        score = 0.0

        # Has meaningful tags
        if len(tags) >= 3:
            score += 0.3
        elif len(tags) >= 1:
            score += 0.15

        # Content mentions intent-related keywords
        if intent and intent.lower() in content.lower():
            score += 0.2

        # Cross-reference: other entries don't duplicate this one
        # (simplified: check if title/content is unique enough)
        title = entry.get("title", "")
        if len(title) > 10:
            score += 0.2

        # Addresses a specific topic (not vague)
        vague_words = ['things', 'stuff', 'etc', 'various', 'different']
        if not any(v in content.lower() for v in vague_words):
            score += 0.15

        return min(1.0, score)

    def _grade(self, score: float) -> str:
        if score >= 0.85:
            return "A"
        elif score >= 0.70:
            return "B"
        elif score >= 0.55:
            return "C"
        elif score >= 0.40:
            return "D"
        else:
            return "F"

    def _recommendations(self, scores: dict, entry: dict) -> list[str]:
        recs = []
        if scores["completeness"] < 0.5:
            recs.append("Expand content — add more detail, steps, or examples")
        if scores["clarity"] < 0.5:
            recs.append("Simplify language — use shorter sentences and clear instructions")
        if scores["freshness"] < 0.5:
            recs.append("Review and update — content may be outdated")
        if scores["usage_effectiveness"] < 0.4:
            recs.append("Low user satisfaction — consider rewriting or replacing")
        if scores["coverage"] < 0.5:
            recs.append("Add more tags and intent-specific keywords")
        if not recs:
            recs.append("Entry is healthy — no changes needed")
        return recs


# Import for Counter
from collections import Counter
