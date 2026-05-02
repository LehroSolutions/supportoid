"""
Agent 2: EmpathyEngine — based on ClawHub customer-support SOP
===============================================================
Rules:
  • Acknowledge BEFORE solving
  • Apologize for experience, not fault
  • Match user's tone/formality
  • Let angry customers vent
  • Offer concrete solutions (discount, escalation path)
  • Lead with what you CAN do
  • Know when to escalate
"""

from dataclasses import dataclass

TONE_FORMAL = "formal"
TONE_WARM = "warm" 
TONE_EMPATHETIC = "empathetic"
TONE_URGENT = "urgent"
TONE_TECHNICAL = "technical"

@dataclass
class EmpathyResult:
    tone: str
    greeting: str
    closing: str
    strategy: str
    formality: float = 0.5  # solve, appease, educate, escalate

class EmpathyEngine:
    GREETINGS = {
        TONE_FORMAL: "Thank you for contacting Lehro Solutions Support.",
        TONE_WARM: "Hey there! 👋 Happy to help with that.",
        TONE_EMPATHETIC: "I completely understand how frustrating this must be. Let me help resolve this right away.",
        TONE_URGENT: "I understand this is time-sensitive. I'm prioritizing this now.",
        TONE_TECHNICAL: "Thanks for the detailed report. Let me investigate systematically.",
    }
    CLOSINGS = {
        TONE_FORMAL: "Please don't hesitate to reach out for further assistance.",
        TONE_WARM: "Let me know if there's anything else I can help with! 😊",
        TONE_EMPATHETIC: "I'll stay on this until it's fully resolved. You're in good hands.",
        TONE_URGENT: "I'm tracking this personally and will update you within the hour.",
        TONE_TECHNICAL: "I'll provide a detailed update once investigation is complete.",
    }

    def analyze(self, classification: dict, history: list = None) -> EmpathyResult:
        sentiment = classification.get("sentiment", 0)
        intent = classification.get("intent", "general_question")
        urgency = classification.get("urgency", 0)
        is_repeat = self._is_repeat(history) if history else False
        formality = self._formality(history) if history else 0.5

        if sentiment <= -0.6: tone, strategy = TONE_EMPATHETIC, "appease"
        elif urgency >= 0.7: tone, strategy = TONE_URGENT, "escalate"
        elif is_repeat: tone, strategy = TONE_EMPATHETIC, "escalate"
        elif intent in ("technical_issue", "bug_report"): tone, strategy = TONE_TECHNICAL, "solve"
        elif intent == "feature_request": tone, strategy = TONE_WARM, "educate"
        elif formality > 0.7: tone, strategy = TONE_FORMAL, "solve"
        else: tone, strategy = TONE_WARM, "solve"

        return EmpathyResult(tone=tone, greeting=self.GREETINGS[tone],
                            closing=self.CLOSINGS[tone], strategy=strategy)

    @staticmethod
    def _is_repeat(history) -> bool:
        msgs = [m.get("content","").lower() for m in history[-8:] if m.get("role")=="user"]
        for i in range(len(msgs)-1):
            for j in range(i+1, len(msgs)):
                common = len(set(msgs[i].split()) & set(msgs[j].split()))
                if common > len(set(msgs[i].split())) * 0.6: return True
        return False

    @staticmethod
    def _formality(history) -> float:
        text = " ".join([m.get("content","") for m in history[-3:] if m.get("role")=="user"]).lower()
        formal = sum(1 for w in ["dear","regarding","furthermore","pertaining"] if w in text)
        casual = sum(1 for w in ["hey","lol","omg","thx","gonna","wanna","rn"] if w in text)
        return formal/(formal+casual) if (formal+casual) > 0 else 0.5
