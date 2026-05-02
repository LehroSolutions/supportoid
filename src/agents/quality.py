"""
Agent 6: QualityAssurance — Pre-send Scoring
=============================================
Scores every response before it reaches user.
Checks: empathy alignment, accuracy, completeness, tone match, safety.
Prevents bad/unsafe/incomplete responses from being sent.
"""

from dataclasses import dataclass

@dataclass
class QualityScore:
    overall: float
    empathy: float
    accuracy: float
    completeness: float
    tone_match: float
    safety: float
    flagged_issues: list

SAFE_PREFIXES = {"i understand", "i'm sorry", "i hear you", "let me help", "happy to help", "thanks for", "great question", "welcome", "i completely understand", "i appreciate"}
UNSAFE_PATTERNS = {"guaranteed", "100% sure", "will definitely fix", "your fault", "you should have", "that's not our problem", "policy says", "can't help you", "no can do", "for sure"}

class QualityAssurance:
    """
    Validates response quality before sending.
    From agent-evaluation skill: behavioral contract testing + safety checks.
    """
    MIN_ACCEPTABLE = 0.4

    def score(self, response: str, classification: dict, empathy) -> QualityScore:
        sentiment = classification.get("sentiment", 0)
        lower = response.lower()
        issues = []

        # Empathy
        empathy_score = 0.5
        if sentiment < -0.3:
            if any(w in lower for w in ["understand", "sorry", "frustrating", "help", "apologize"]): empathy_score += 0.3
            else: empathy_score -= 0.2; issues.append("Missing empathy for negative sentiment")
        elif sentiment > 0.3:
            if any(w in lower for w in ["great", "happy", "glad", "wonderful"]): empathy_score += 0.1
        if len(response.split()) < 15: empathy_score -= 0.2; issues.append("Too short")

        # Accuracy
        accuracy = 0.6
        if any(w in lower for w in ["guaranteed", "100%", "always", "never"]): accuracy -= 0.2; issues.append("Makes absolute claims")
        if any(w in lower for w in ["steps", "go to", "settings", "click", "navigate"]): accuracy += 0.2
        if any(w in lower for w in ["let me check", "might", "could be"]): accuracy += 0.1

        # Completeness
        wc = len(response.split())
        completeness = min(1.0, wc / 100)
        if wc < 20: issues.append("Response may be incomplete")

        # Tone match
        tone_score = 0.6
        if sentiment < -0.5 and any(w in lower for w in ["😊", "😄", "haha", "lol", "no worries"]): tone_score -= 0.3; issues.append("Tone mismatch — too casual for upset user")
        if any(m in response for m in ["\n•", "\n1.", "\n**", "Step"]): tone_score += 0.2

        # Safety
        safety = 1.0
        for word in UNSAFE_PATTERNS:
            if word in lower: safety -= 0.3; issues.append(f"Unsafe pattern: '{word}'")

        overall = empathy_score*0.2 + accuracy*0.25 + completeness*0.25 + tone_score*0.15 + safety*0.15
        return QualityScore(
            overall=max(0, min(1, overall)),
            empathy=max(0, min(1, empathy_score)),
            accuracy=max(0, min(1, accuracy)),
            completeness=max(0, min(1, completeness)),
            tone_match=max(0, min(1, tone_score)),
            safety=max(0, min(1, safety)),
            flagged_issues=issues,
        )
