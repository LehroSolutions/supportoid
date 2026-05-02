"""Agent 6: EscalationEngine — Human Handoff Decision"""
from dataclasses import dataclass

@dataclass
class EscalationDecision:
    should_escalate: bool
    reason: str
    priority: str
    human_role: str
    suggested_action: str

KEYWORDS = {
    "human_request": {"human", "person", "manager", "supervisor", "real person", "speak to someone", "talk to", "not a bot"},
    "security": {"data breach", "personal data", "gdpr", "ccpa", "hipaa", "hack", "unauthorized access", "stolen credentials"},
    "legal": {"lawsuit", "lawyer", "legal team", "complaint to", "regulator", "attorney", "class action"},
    "financial": {"chargeback", "dispute", "fraud", "overcharged", "unauthorized charge"},
}

class EscalationEngine:
    def evaluate(self, message: str, classification: dict, quality_score: float, history: list = None) -> EscalationDecision:
        triggers = []; score = 0; human_role = "support_agent"
        lower = message.lower()

        # 1. Keyword escalation
        for cat, words in KEYWORDS.items():
            for w in words:
                if w in lower:
                    triggers.append(f"{cat}: '{w}'")
                    score += {"security":40,"legal":45,"human_request":30,"financial":20}[cat]
                    human_role = {"security":"security_team","legal":"compliance_officer","human_request":"specialist","financial":"billing_specialist"}[cat]
                    break

        # 2. Sentiment trajectory
        if history:
            sentiments = [m.get("sentiment",0) for m in history if m.get("role")=="user" and "sentiment" in m]
            if len(sentiments) >= 2 and sentiments[-1] < sentiments[0] - 0.3:
                triggers.append(f"Sentiment worsening")
                score += 20

        # 3. Low confidence AI
        conf = classification.get("confidence", 1.0)
        if conf < 0.3:
            triggers.append(f"Very low confidence: {conf:.2f}")
            score += 20
        elif conf < 0.5:
            if "Low confidence" not in str(triggers): score += 5

        # 4. Poor quality response
        if quality_score < 0.3:
            triggers.append(f"Low quality: {quality_score:.2f}")
            score += 20
        elif quality_score < 0.5:
            score += 5

        # 5. Long unresolved conversation
        if history:
            total_msgs = len(history)
            if total_msgs > 6:
                score += 15
                if total_msgs > 10: score += 10
                triggers.append(f"Long conversation: {total_msgs} messages")

        priority = "critical" if score >= 50 else "high" if score >= 30 else "medium" if score >= 15 else "low"
        should = score >= 20
        suggested = f"Escalate to {human_role} (priority: {priority})" if should else ""
        if should and priority == "critical": suggested += " — Immediate attention required"

        return EscalationDecision(should_escalate=should,
            reason="; ".join(triggers) or "No escalation triggers",
            priority=priority, human_role=human_role, suggested_action=suggested)
