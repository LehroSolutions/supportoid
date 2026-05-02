"""
Agent 7: FeedbackAnalyst — Continuous Self-Improvement
======================================================
From `feedback-loop-fine-tuner` + `customer-feedback` ClawHub skills.

• Every interaction is recorded and scored
• Identifies gaps in AI performance
• Auto-collects training data from user corrections
• Triggers model retraining when enough corrected data exists
• Reports quality metrics over time
"""

import json, os, logging
from datetime import datetime, timedelta, timezone

from src.app.redaction import redact_text
from src.app.timeutils import utc_now, utc_now_iso

logger = logging.getLogger("supportoid.feedback")

class FeedbackAnalyst:
    def __init__(self, settings):
        self.feedback_dir = settings.feedback_dir if hasattr(settings, 'feedback_dir') else "./data/feedback"
        self.training_dir = settings.training_dir if hasattr(settings, 'training_dir') else "./data/training"
        os.makedirs(self.feedback_dir, exist_ok=True)
        os.makedirs(self.training_dir, exist_ok=True)
        self.entries = []
        self._load()

    def _load(self):
        for fn in os.listdir(self.feedback_dir):
            if fn.endswith(".jsonl"):
                with open(os.path.join(self.feedback_dir, fn)) as f:
                    for line in f:
                        try: self.entries.append(json.loads(line))
                        except: pass
        logger.info(f"Loaded {len(self.entries)} feedback entries")

    def record(self, message: str, classification: dict, response_result: dict, quality_score: float = 0.0,
              user_rating: int = 0, corrected_intent: str = ""):
        """Record a single interaction for analysis and learning."""
        entry = {
            "id": f"fb_{len(self.entries)}",
            "timestamp": utc_now_iso(),
            "message_preview": redact_text(message[:200]),
            "predicted_intent": classification.get("intent", "unknown"),
            "confidence": classification.get("confidence", 0),
            "sentiment": classification.get("sentiment", 0),
            "response": redact_text(response_result.get("response", "")[:500]),
            "response_source": response_result.get("source", "unknown"),
            "quality_score": quality_score,
            "user_rating": user_rating,
            "corrected_intent": corrected_intent if corrected_intent else "",
        }
        # Auto-decide action — corrected_intent takes priority (valuable training signal)
        if corrected_intent:
            entry["auto_action"] = "add_to_training"
            self._add_training_correction(message, corrected_intent)
        elif user_rating <= 2: entry["auto_action"] = "flag_for_review"
        elif quality_score < 0.3: entry["auto_action"] = "needs_improvement"
        elif quality_score >= 0.7 and user_rating >= 4: entry["auto_action"] = "quality_example"
        else: entry["auto_action"] = "none"

        self.entries.append(entry)
        self._append_to_file(entry)

    def _add_training_correction(self, message: str, corrected_intent: str):
        correction = {
            "message": redact_text(message[:500]),
            "correct_intent": corrected_intent,
            "time": utc_now_iso(),
        }
        path = os.path.join(self.training_dir, "corrections.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(correction) + "\n")

    def _append_to_file(self, entry: dict):
        today = utc_now().strftime("%Y-%m-%d")
        path = os.path.join(self.feedback_dir, f"feedback-{today}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_training_data(self, min_samples: int = 10) -> list[dict]:
        """Extract corrected feedback for model retraining."""
        path = os.path.join(self.training_dir, "corrections.jsonl")
        data = []
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try: data.append(json.loads(line))
                    except: pass
        if len(data) < min_samples:
            logger.info(f"Not enough training data: {len(data)} < {min_samples}")
            return []
        return data

    def clear_training_data(self):
        path = os.path.join(self.training_dir, "corrections.jsonl")
        if os.path.exists(path):
            os.remove(path)

    def get_quality_report(self, days: int = 7) -> dict:
        cutoff = utc_now() - timedelta(days=days)
        recent = []
        for entry in self.entries:
            parsed = datetime.fromisoformat(entry["timestamp"])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= cutoff:
                recent.append(entry)
        if not recent: return {"period_days": days, "total": 0}
        ratings = [e["user_rating"] for e in recent if e.get("user_rating", 0) > 0]
        avg = sum(ratings) / len(ratings) if ratings else None
        satisfaction = round(len([r for r in ratings if r >= 4]) / len(ratings) * 100, 1) if ratings else None
        return {
            "period_days": days, "total": len(recent), "avg_rating": avg, "satisfaction_rate": satisfaction,
            "flagged": len([e for e in recent if e.get("auto_action") == "flag_for_review"]),
            "improvements_needed": len([e for e in recent if e.get("auto_action") == "needs_improvement"]),
            "quality_examples": len([e for e in recent if e.get("auto_action") == "quality_example"]),
            "corrections_saved": len(self.get_training_data(min_samples=1)),
        }

    @property
    def total_count(self): return len(self.entries)
