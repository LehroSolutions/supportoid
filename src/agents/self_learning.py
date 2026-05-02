"""
Self-Learning from User Feedback
=================================
Enhances the FeedbackAnalyst with:
  • Automatic KB entry creation from escalated conversations
  • Feedback-driven quality score recalibration
  • Pattern detection in low-rated responses
  • Auto-suggestion of KB gaps
  • Continuous learning loop integration

Feeds back into KnowledgeRetriever to improve RAG results over time.
"""

import json
import os
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.app.timeutils import utc_now, utc_now_iso

logger = logging.getLogger("supportoid.selflearning")


class SelfLearningEngine:
    """Learns from user feedback to improve KB and responses autonomously."""

    def __init__(self, feedback_dir: str, kb_dir: str, training_dir: str):
        self.feedback_dir = feedback_dir
        self.kb_dir = kb_dir
        self.training_dir = training_dir
        os.makedirs(feedback_dir, exist_ok=True)
        os.makedirs(kb_dir, exist_ok=True)
        os.makedirs(training_dir, exist_ok=True)
        self.learning_log: list[dict] = []

    def load_feedback_entries(self, days: int = 30) -> list[dict]:
        """Load recent feedback entries for analysis."""
        entries = []
        cutoff = utc_now() - timedelta(days=days)
        if not os.path.isdir(self.feedback_dir):
            return entries
        for fn in os.listdir(self.feedback_dir):
            if not fn.endswith(".jsonl"):
                continue
            with open(os.path.join(self.feedback_dir, fn)) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        ts = e.get("timestamp", "")
                        if ts:
                            parsed = datetime.fromisoformat(ts)
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            if parsed >= cutoff:
                                entries.append(e)
                    except Exception:
                        pass
        return entries

    def analyze_feedback_patterns(self, entries: list[dict]) -> dict:
        """Find patterns in low-rated responses and KB gaps."""
        if not entries:
            return {"total_analyzed": 0}

        low_rated = [e for e in entries if e.get("user_rating", 5) <= 2]
        high_rated = [e for e in entries if e.get("user_rating", 0) >= 4]
        flagged = [e for e in entries if e.get("auto_action") in ("flag_for_review", "needs_improvement")]

        # Intent distribution for low-rated
        intent_counter = Counter(e.get("predicted_intent", "unknown") for e in low_rated)
        # Common response sources
        source_counter = Counter(e.get("response_source", "unknown") for e in low_rated)
        # Quality score distribution
        low_quality = [e for e in entries if e.get("quality_score", 1.0) < 0.5]

        # Detect potential KB gaps — intents with low ratings and few KB hits
        gap_intents = []
        for intent, count in intent_counter.most_common(5):
            if count >= 2:
                gap_intents.append({
                    "intent": intent,
                    "low_ratings": count,
                    "action": "Suggest creating KB entries for this intent"
                })

        return {
            "total_analyzed": len(entries),
            "low_rated_count": len(low_rated),
            "high_rated_count": len(high_rated),
            "flagged_count": len(flagged),
            "low_quality_count": len(low_quality),
            "problem_intents": dict(intent_counter.most_common(5)),
            "problem_sources": dict(source_counter.most_common(3)),
            "kb_gaps": gap_intents,
            "recommendations": self._generate_recommendations(intent_counter, source_counter, len(low_rated), len(entries)),
        }

    def _generate_recommendations(self, intent_counter, source_counter, low_count, total) -> list[str]:
        recs = []
        if total == 0:
            return ["Collect more feedback data to enable learning."]

        low_pct = low_count / total * 100
        if low_pct > 30:
            recs.append("High low-rating rate ({:.0f}%) — review response templates".format(low_pct))
        for intent, count in intent_counter.most_common(3):
            if count >= 2:
                recs.append(f"Create KB entries for '{intent}' (flagged {count} times)")

        top_source = source_counter.most_common(1)
        if top_source and top_source[0][0] == "llm" and top_source[0][1] > len([e for e in []]) :
            recs.append("LLM fallback used frequently — expand KB coverage")

        if not recs:
            recs.append("No critical gaps detected. Continue monitoring.")
        return recs

    def auto_create_kb_from_feedback(self, feedback_entries: list[dict], knowledge_retriever) -> list[str]:
        """
        Automatically suggest KB entries from common unanswered questions.
        Looks for messages that triggered escalation or low ratings with no KB results.
        """
        created = []
        # Group by similar intent that had no good KB results
        unanswered = [
            e for e in feedback_entries
            if e.get("user_rating", 5) <= 2
            and e.get("auto_action") in ("flag_for_review", "needs_improvement")
        ]

        # Group by intent
        intent_groups: dict[str, list[dict]] = {}
        for e in unanswered:
            intent = e.get("predicted_intent", "unknown")
            intent_groups.setdefault(intent, []).append(e)

        for intent, group in intent_groups.items():
            if len(group) >= 2:  # At least 2 similar complaints
                # Extract common themes from message previews
                messages = [e.get("message_preview", "") for e in group]
                common_words = self._extract_common_terms(messages)

                if common_words:
                    title = f"FAQ: Common {intent} Questions"
                    content = f"Based on user feedback patterns:\n" + "\n".join(
                        f"• {m[:120]}" for m in messages[:3]
                    )
                    tags = list(common_words)[:5] + [intent]

                    eid = knowledge_retriever.add_entry(title, content, intent, tags)
                    created.append(eid)
                    self._log_learning("kb_auto_create", {
                        "entry_id": eid,
                        "title": title,
                        "source_intent": intent,
                        "feedback_count": len(group)
                    })

        return created

    def _extract_common_terms(self, messages: list[str]) -> set[str]:
        """Extract common meaningful terms across messages."""
        from src.agents.rag_retrieval import tokenize
        all_tokens = []
        for msg in messages:
            all_tokens.extend(tokenize(msg))
        counter = Counter(all_tokens)
        return {t for t, c in counter.most_common(10) if c >= 2}

    def recalibrate_quality_scores(self, feedback_entries: list[dict]) -> dict[str, float]:
        """
        Recalibrate KB entry quality scores based on aggregated feedback.
        Returns {entry_id: new_quality_score} for entries that had significant feedback.
        """
        # Group feedback by which KB entries were actually used
        # This is a simplified version — in production we'd track which KB entries
        # were returned in each conversation
        entry_ratings: dict[str, list[int]] = {}

        for e in feedback_entries:
            rating = e.get("user_rating", 0)
            if rating > 0:
                # Attribute to the most relevant intent-based entries
                intent = e.get("predicted_intent", "unknown")
                entry_ratings.setdefault(intent, []).append(rating)

        recalibrated = {}
        for key, ratings in entry_ratings.items():
            if len(ratings) >= 2:
                avg = sum(ratings) / len(ratings)
                new_quality = min(1.0, avg / 5.0)  # Normalize 1-5 to 0-1
                recalibrated[key] = round(new_quality, 3)

        return recalibrated

    def _log_learning(self, action: str, details: dict):
        """Log a learning action for auditability."""
        entry = {
            "timestamp": utc_now_iso(),
            "action": action,
            **details
        }
        self.learning_log.append(entry)
        path = os.path.join(self.training_dir, "learning_log.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_learning_report(self) -> dict:
        """Summary of all learning actions taken."""
        return {
            "total_learning_actions": len(self.learning_log),
            "recent_actions": self.learning_log[-10:],
            "auto_kb_entries_created": sum(
                1 for l in self.learning_log if l.get("action") == "kb_auto_create"
            ),
            "quality_recalibrations": sum(
                1 for l in self.learning_log if l.get("action") == "quality_recalibration"
            ),
        }
