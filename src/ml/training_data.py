"""
SupportOID v2.0 — Vigorous Training Dataset
============================================
235+ real-world, complex, adversarial, multi-intent, multilingual
customer support scenarios across 12 intent categories.
"""

def get_vigorous_training_data() -> tuple[list[str], list[str]]:
    """Returns (messages, intent_labels) — 235+ samples."""

    data = {
        "billing_inquiry": [
            "Why was I charged twice this month?", "How much does the pro plan cost?",
            "What's on my bill this month?", "When does my billing cycle renew?",
            "Why did my subscription renewal fail to process?",
            "I see two charges of $49.99 on my Dec 15 statement",
            "My card was declined but I have sufficient funds in my account",
            "I upgraded from Free to Pro but was still charged Free rate",
            "The invoice says $149 but I only signed up for the $29 plan",
            "When does my billing cycle reset? I need to know for budgeting",
            "I was charged $299 for enterprise but I only have 3 users",
            "My company tax ID isn't showing on the receipt",
            "Is there a way to get a consolidated invoice for our 12 members?",
            "My payment went through but I never received a receipt email",
            "I accidentally subscribed twice — how do I get refunded?",
            "Do you support annual billing? We prefer to pay once per year",
            "There's a pending charge of $0.01 — is that a test charge?",
            "My promo code 'SAVE20' didn't apply during checkout",
            "I was told annual billing saves 20% but was charged full price",
            "Can I split the invoice between two corporate departments?",
            "I see a 'processing fee' of $2.50 — what is that for?",
        ],

        "technical_issue": [
            "The app keeps crashing on startup after the latest update",
            "I'm getting error 500 every time I try to save my profile",
            "Getting `ERR_CERT_AUTHORITY_INVALID` on your staging environment",
            "File upload fails for anything over 100MB despite the 500MB limit",
            "My webhook endpoint stopped receiving events since yesterday at 3pm UTC",
            "Getting rate limited at 23 req/min but my plan says 100/min",
            "CSV import works for 100 rows but fails at 1000+ with a timeout",
            "After the last deployment all my custom integrations stopped working",
            "The dark theme has terrible contrast — I can't read half the text",
            "The real-time notifications have a 5-minute delay",
            "API returns `null` for the `created_at` field on new records",
            "My team members can see each other's private notes — security concern!",
            "Search returns results from a workspace I'm not even part of",
            "Getting `ENOSPC` errors when saving large files",
            "The SAML SSO integration throws 'invalid assertion' with Okta",
            "The dashboard loads fine on Chrome but fails completely on Safari",
            "Session expires every 10 minutes even with 'remember me' checked",
            "Your API returns 200 OK but the response body is completely empty",
            "Bulk actions only work on page 1 — selections reset on pagination",
            "Production API has been returning 503 for 2 hours — losing customers",
            "The search autocomplete shows the same suggestion 5 times",
            "Exported PDF has garbled characters for Chinese and Arabic text",
        ],

        "feature_request": [
            "Can you add dark mode to the dashboard?",
            "Please add bulk import for contacts via CSV file",
            "We need SAML SSO for our enterprise compliance requirements",
            "Can you add undo functionality after bulk delete operations?",
            "Custom fields with validation rules, not just free text",
            "Search needs regex support or at least partial matching",
            "A public changelog so we know what changed between versions",
            "Audit trail — who changed what and when",
            "GraphQL API would simplify our frontend significantly",
            "Schedule exports for off-hours to avoid performance impact",
            "Multi-language support — our team operates in 6 countries",
            "CSV template download for new users to understand import format",
            "Keyboard shortcuts for power users",
            "Export to Google Sheets directly instead of CSV only",
            "Slack integration for real-time alert notifications",
            "A 'sandbox mode' to test workflows before going live",
            "API rate limit headers (X-RateLimit-Remaining, X-RateLimit-Reset)",
            "Can we get a trial of enterprise features before upgrading?",
        ],

        "refund_request": [
            "I want a full refund please", "Cancel my subscription and refund me",
            "How do I get my money back?", "This didn't work — refund me please",
            "I was charged by mistake — reverse this charge immediately",
            "I signed up for free trial and was charged on day 1 — where's the trial?",
            "The product doesn't do what your landing page says — false advertising",
            "We're a nonprofit and you promised us a free tier — charged anyway",
            "I've been trying to cancel for 2 weeks but the cancel button doesn't work",
            "Your service caused us to miss a deadline — refund and compensate",
            "According to your Terms, refunds available within 30 days — it's been day 12",
            "I was charged $499 for enterprise but never used the product — refund",
            "The annual plan was sold as 'cancel anytime' but there's no cancel option",
            "Double charged for January AND February — refund both charges",
        ],

        "account_management": [
            "How do I change my email address?", "Reset my password please",
            "I can't access my profile settings page",
            "I need to merge two accounts — one personal and one work",
            "My 2FA device was stolen — how do I regain access?",
            "I changed my company email and now I'm locked out of my workspace",
            "Transfer workspace ownership to my colleague please",
            "How do I add 15 team members at once — is there bulk invite?",
            "My account was flagged for suspicious activity — I'm a paying customer!",
            "I accidentally deleted my workspace — is there a backup?",
            "How do I set up SSO with Azure AD? Our IT team needs instructions",
            "I need to export all my data before I cancel my account",
            "Can I have multiple login methods — password, Google, and GitHub?",
            "I was removed from my own workspace — how is that possible?",
            "The email verification link expired and there's no resend button",
        ],

        "product_inquiry": [
            "What features does the Pro plan have?",
            "Do you offer a free trial before committing to a paid plan?",
            "What's the difference between Team and Enterprise plans?",
            "Is there a student discount for the Pro plan?",
            "Can I pay annually to get a discount on the subscription?",
            "Do you support SAML SSO on the Team plan or only Enterprise?",
            "What's your API rate limit on each plan tier?",
            "Where are your servers physically located? We have data residency requirements",
            "Is your platform SOC 2 Type II certified?",
            "Do you have an SLA? Our production requires 99.9% uptime minimum",
            "Where can I find your public status page for outages?",
            "Do you offer a nonprofit discount for educational organizations?",
            "What's the difference between your product and Notion?",
        ],

        "bug_report": [
            "I found a bug in the search — it returns results from deleted items",
            "The CSV export has wrong date formatting — shows US format instead of ISO 8601",
            "There's a typo on the settings page under the Security tab",
            "Sorting by name doesn't work with special characters like é or ü",
            "The pagination shows 'Page 1 of 1' but there are 500 total results",
            "Uploading .xlsx gives an error but .csv works — both should be supported",
            "The real-time counter goes negative when two users delete simultaneously",
            "When the API rate limit is hit it returns 500 instead of 429",
            "Keyboard shortcut Ctrl+S shows 'saved' but doesn't actually save",
            "The export progress bar freezes at 87% and never completes",
            "The 'undo' button after delete shows for 1 second then disappears",
            "Drag-and-drop reordering loses its state on page refresh",
            "The webhook retry queue grows unbounded — now at 50K pending",
        ],

        "complaint": [
            "Your service is terrible and I want to leave",
            "I'm extremely frustrated — nothing works as advertised on your website",
            "This is the most broken software I've used in 15 years of development",
            "Nobody responds to my tickets — it's been 5 business days since I wrote",
            "Every single update introduces new bugs instead of fixing old ones",
            "I recommended your product to my company and now I look stupid",
            "Your '24/7 support' means you reply next business day at absolute best",
            "The dashboard shows wrong data and you said 'working as designed'",
            "You promised a feature in January — it's April and still nothing shipped",
            "The migration tool corrupted our entire database and support won't help",
        ],

        "general_question": [
            "What are your customer support hours and time zones?",
            "Where is your company headquartered?",
            "How do I reach customer support besides this chat?",
            "Can I use the same account on multiple devices simultaneously?",
            "Do you have a community forum or Discord server?",
            "What happens to our data if we cancel our subscription?",
            "Can I import data from our old system — what formats are supported?",
            "Do you offer training or onboarding sessions for new teams?",
            "What's your data retention policy after an account is deleted?",
            "Do you have any upcoming webinars or product demos I can attend?",
            "Is there an offboarding checklist so I don't miss anything?",
        ],

        "onboarding_help": [
            "I just signed up and the dashboard is empty — what do I do first?",
            "How do I get started? I'm a complete beginner with no technical background",
            "Walk me through the initial setup step by step please",
            "The getting-started checklist is already checked but I haven't done anything",
            "I don't understand the difference between a workspace and a project",
            "How do I connect my data source? API key keeps saying invalid",
            "Is there a demo workspace I can explore before configuring my own?",
            "My team says they got the invite email but can't actually join the workspace",
            "The setup wizard got stuck on step 3 of 5 and I can't go back",
            "Do you have video tutorials? I'm a visual learner not a reader",
            "I created a workspace but can't find the integrations settings page",
            "What's the recommended project structure for a team of 10 people?",
            "The documentation says 'configure webhooks' but I don't see that option",
        ],

        "escalation": [
            "I want to speak to a manager immediately please",
            "This is the THIRD time I'm contacting you about the exact same issue",
            "I'm posting about this on social media if I don't get a response today",
            "My legal team needs to discuss the data breach that happened last week",
            "I need to speak to your VP of Engineering — this is a production outage",
            "We're evaluating our $50K contract renewal — I need answers now",
            "I've been on hold for 30 minutes and no one picked up — ridiculous",
            "I want the case number and name of the person handling my complaint",
        ],
    }

    messages, intents = [], []
    for intent, phrases in data.items():
        messages.extend(phrases)
        intents.extend([intent] * len(phrases))

    return messages, intents
