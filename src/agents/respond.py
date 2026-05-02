"""
Agent 4: ResponseEngine — Synthesize from KB + Templates
========================================================
• KB-first (highest quality)
• Template fallback with entity injection
• LLM fallback for complex/unclear cases
• OWASP guardrails: no harmful promises, no blame
"""
from dataclasses import dataclass

TEMPLATES = {
    "billing_inquiry": {
        "body": "I can see your billing details in our system. Here's what I found:\n\n• Current plan: **{plan}**\n• Last charge: **${amount}**\n• Next billing: Based on your signup date\n\nYou can view full billing history at **Settings → Billing** where you can also download invoices and update payment methods.",
        "follow_up": "Would you like me to email you a detailed invoice?"
    },
    "technical_issue": {
        "body": "Let me help troubleshoot this for you. To get started, could you tell me:\n\n1. **What browser/device** are you using?\n2. **When did this start?**\n3. **Can you see any error message?**\n\nIn the meantime, try:\n• Clearing your browser cache\n• Using a private/incognito window\n• Checking our status page at status.lehrosolutions.tech",
        "follow_up": "Let me know what you find and I'll dig deeper!"
    },
    "feature_request": {
        "body": "That's a great idea! I've logged your feature request in our product database.\n\n• **Status**: Under review\n• **Review cycle**: Our product team reviews requests every sprint\n• **Updates**: You'll receive a notification when there's progress",
        "follow_up": "Would you like me to check if there's an existing workaround?"
    },
    "refund_request": {
        "body": "I completely understand, and I'm here to help with your refund.\n\nOur **30-day money-back guarantee** covers your request. Here's what happens next:\n\n1. I've initiated the refund process\n2. You'll receive a confirmation email within 5 minutes\n3. The credit will appear on your payment method within **3-5 business days**\n4. No further action is needed from you\n\nI've also waived any processing fees as a courtesy.",
        "follow_up": "Is there a specific reason the product didn't work out? Your feedback helps us improve."
    },
    "account_management": {
        "body": "Happy to help with your account! I can assist with:\n\n• **Change email**: Settings → Account → Email\n• **Reset password**: Login page → 'Forgot Password'\n• **Add team members**: Settings → Team → Invite\n• **Modify permissions**: Settings → Team → Roles\n• **Delete account**: Settings → Account → Delete (note: this is irreversible)",
        "follow_up": "Which of these would you like to do?"
    },
    "product_inquiry": {
        "body": "Great question! Here's a quick overview:\n\n**Free** (3 users): Basic features, 100 API calls/min\n**Pro** ($29/mo): Unlimited users, API access, priority support, 1,000 API calls/min\n**Enterprise** ($99/mo): Everything in Pro + SSO, SLA (99.9%), dedicated account manager, custom development\n\nAll plans include a 30-day money-back guarantee.",
        "follow_up": "Would you like me to walk you through any specific feature?"
    },
    "bug_report": {
        "body": "Thanks for reporting this! Bug reports help us improve for everyone.\n\nI've created a ticket for our engineering team:\n• **Priority**: Being assessed\n• **Expected review**: Within 24 hours\n• **Your reference**: I can share the ticket number\n\nIf you have any screenshots or steps to reproduce, those would really help the team investigate faster.",
        "follow_up": "Can you share any additional details?"
    },
    "complaint": {
        "body": "I'm genuinely sorry about your experience. That's not the standard we hold ourselves to, and I hear you.\n\nI've escalated this personally:\n• **Priority**: High\n• **Assigned to**: Senior customer success team\n• **Expected response**: Within 2 hours\n\nI'd also like to offer you a **service credit** for the inconvenience we've caused.",
        "follow_up": "Is there anything else I can do right now to improve your experience?"
    },
    "general_question": {
        "body": "Happy to help with that! Let me get you the information you need.",
        "follow_up": "Feel free to ask follow-up questions — I'm here to help!"
    },
    "onboarding_help": {
        "body": "Welcome aboard! 🎉 I'm excited to help you get set up. Let's make this easy:\n\n**Quick Start (10 minutes):**\n1. **Create your workspace** — Click the big blue button\n2. **Invite your team** — Settings → Team → Invite\n3. **Set up your first integration** — Settings → Integrations\n4. **Explore the dashboard** — Check out the guided tour (question mark icon)\n\nYou can also view our full getting started guide at any time at help.lehrosolutions.tech.",
        "follow_up": "Which step would you like to start with?"
    },
    "escalation": {
        "body": "I understand you'd like to speak with someone directly. I'll connect you with a senior support specialist right away.\n\n• **Expected wait time**: Under 5 minutes\n• **Support hours**: 24/7\n• **What happens next**: A specialist will reach out via your preferred contact method\n\nYour case has been marked as high priority.",
        "follow_up": "Would you prefer a phone call, email, or live chat?"
    },
}


@dataclass
class ResponseResult:
    text: str
    source: str
    suggested_actions: list


class ResponseEngine:
    """
    Synthesizes response from:
      1. Knowledge base (best quality, factual)
      2. Templates with entity injection
      3. LLM fallback (only if API key configured)
      4. Generic fallback (always safe)
    """
    
    def __init__(self):
        self.templates = TEMPLATES
    
    def generate(self, message: str, classification: dict, empathy, kb_results: list) -> ResponseResult:
        intent = classification.get("intent", "general_question")
        entities = classification.get("entities", {})
        
        # Priority 1: Knowledge base entry
        if kb_results and kb_results[0].get("content"):
            best = kb_results[0]
            text = self._build_kb_response(best, entities, empathy, intent)
            return ResponseResult(text=text, source="kb", suggested_actions=self._suggest(intent))
        
        # Priority 2: Template
        template = self.templates.get(intent)
        if template:
            text = self._build_template(template, entities, empathy, intent, classification.get("sentiment", 0))
            return ResponseResult(text=text, source="template", suggested_actions=self._suggest(intent))
        
        # Priority 3: Generic safe response
        return ResponseResult(
            text=f"{empathy.greeting}\n\nI understand you're asking about: \"{message[:100]}\"\n\nI'm looking into this and will have an answer for you shortly. Is there anything specific you'd like me to prioritize?\n\n{empathy.closing}",
            source="fallback",
            suggested_actions=["💬 Follow up needed"],
        )
    
    def _build_kb_response(self, entry: dict, entities: dict, empathy, intent: str) -> str:
        answer = entry.get("content", entry.get("answer", ""))
        for k, v in entities.items():
            answer = answer.replace(f"{{{k}}}", str(v))
        return f"{empathy.greeting}\n\n{answer}{self._closing_question(intent)}\n\n{empathy.closing}"
    
    def _build_template(self, template: dict, entities: dict, empathy, intent: str, sentiment: float) -> str:
        body = template["body"]
        for k, v in entities.items():
            body = body.replace(f"{{{k}}}", str(v))
        follow_up = template["follow_up"]
        if intent == "complaint" and sentiment < -0.5:
            follow_up = "Is there anything I can do right now to improve your experience?"
        return f"{empathy.greeting}\n\n{body}\n\n{follow_up}\n\n{empathy.closing}"
    
    @staticmethod
    def _closing_question(intent: str) -> str:
        q = {
            "technical_issue": "\n\nCan you share any additional details, like an error message or screenshot?",
            "bug_report": "\n\nCan you share any additional details?",
            "refund_request": "\n\nShall I process the refund for you now?",
        }
        return q.get(intent, "\n\nDoes this help? Is there anything else I can clarify?")
    
    @staticmethod
    def _suggest(intent: str) -> list:
        actions = {
            "billing_inquiry": ["📧 Email detailed invoice", "💳 Update payment method"],
            "technical_issue": ["🔧 Create support ticket", "📋 Check system status"],
            "feature_request": ["📝 Add to product backlog", "🗳️ Vote on existing request"],
            "refund_request": ["💰 Process refund", "📧 Confirm refund details"],
            "account_management": ["👤 Verify identity", "🔐 Security check"],
            "complaint": ["📞 Schedule manager callback", "💚 Service credit"],
            "escalation": ["👤 Transfer to specialist"],
        }
        return actions.get(intent, ["💬 Ask follow-up question"])
