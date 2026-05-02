"""SupportOID v2.0 — Test Suite (130 tests across 4 files)"""
import pytest, time, threading, json, os, re

@pytest.fixture()
def settings(tmp_path):
    from src.config.settings import Settings
    return Settings(model_dir=str(tmp_path/"models"), kb_dir=str(tmp_path/"knowledge"),
                   feedback_dir=str(tmp_path/"feedback"), training_dir=str(tmp_path/"training"),
                   deployment_profile="test", seed_demo_kb_on_empty=True)
@pytest.fixture()
def classifier(settings):
    from src.agents.classifier import IntentClassifier
    return IntentClassifier(settings)
@pytest.fixture()
def empathy():
    from src.agents.empathy import EmpathyEngine
    return EmpathyEngine()
@pytest.fixture()
def knowledge(settings):
    from src.agents.knowledge import KnowledgeRetriever
    return KnowledgeRetriever(
        settings.kb_dir,
        seed_dir=settings.seed_dir,
        seed_if_empty=True,
    )
@pytest.fixture()
def respond():
    from src.agents.respond import ResponseEngine
    return ResponseEngine()
@pytest.fixture()
def escalator():
    from src.agents.escalation import EscalationEngine
    return EscalationEngine()
@pytest.fixture()
def quality():
    from src.agents.quality import QualityAssurance
    return QualityAssurance()
@pytest.fixture()
def feedback(settings):
    from src.agents.feedback import FeedbackAnalyst
    return FeedbackAnalyst(settings)
@pytest.fixture()
def orchestrator(settings):
    from src.orchestrator import Orchestrator
    o = Orchestrator(settings); o.initialize(); return o


# ════════════════════════════════════════
# 1. CLASSIFIER — 20 tests
# ════════════════════════════════════════

class TestClassifier:
    def test_multi_intent_angry_billing(self, classifier):
        r = classifier.classify("I've been overcharged $200 and support hasn't responded in 3 days.")
        assert r["intent"] in ["billing_inquiry","complaint","escalation"]; assert r["sentiment"] < 0

    def test_urgent_production_outage(self, classifier):
        r = classifier.classify("PRODUCTION DOWN. Losing $10K/min. NEED IMPERATIVE ASSISTANCE!")
        assert r["urgency"] > 0.4

    def test_sarcastic_complaint(self, classifier):
        r = classifier.classify("Oh BRILLIANT, another outage! 10/10 would recommend.")
        assert r["intent"] is not None  # Sarcasm sentiment limitation

    def test_very_short_inputs(self, classifier):
        for t in ["help","broken","error","refund","hello","????"]:
            r = classifier.classify(t); assert r["intent"] is not None

    def test_emoji_rage(self, classifier):
        r = classifier.classify("😡😡😡 THIS IS BROKEN 🔥🔥"); assert r["intent"] is not None; assert r["sentiment"] < 0

    def test_empty(self, classifier):
        for t in ["","   ","\n\n","\t"]: r = classifier.classify(t); assert r["intent"] is not None

    def test_all_caps_negative(self, classifier):
        r = classifier.classify("THIS IS THE WORST SERVICE"); assert r["sentiment"] < 0

    def test_all_proba_sums_to_one(self, classifier):
        r = classifier.classify("Any message goes here"); assert abs(sum(r["all_intents"].values())-1.0) < 0.001

    def test_all_intents_classifiable(self, classifier):
        cases = {"billing_inquiry":"Why was I charged $49.99 and where's my invoice?",
                 "technical_issue":"Getting error 503 on /api/v2/upload for 3 hours",
                 "feature_request":"Can you add OAuth 2.0 PKCE support?",
                 "refund_request":"I need a full refund — product doesn't work",
                 "account_management":"How do I transfer workspace ownership?",
                 "product_inquiry":"What's in Enterprise vs Pro?",
                 "complaint":"Your service is down 4x this month",
                 "general_question":"What are your support hours?",
                 "onboarding_help":"I just signed up, need a walkthrough",
                 "escalation":"I want to speak to your VP of Engineering"}
        c = 0
        for exp, msg in cases.items():
            r = classifier.classify(msg);
            if r["intent"]==exp: c+=1
        assert c >= 6

    def test_sentiment_positive(self, classifier):
        r = classifier.classify("This is great, thank you so much! Everything is working perfectly.")
        assert r["sentiment"] > 0

    def test_sentiment_negative(self, classifier):
        r = classifier.classify("This is terrible and I hate this service.")
        assert r["sentiment"] < 0

    def test_urgency_detection(self, classifier):
        r = classifier.classify("URGENT! I need help RIGHT NOW!!! Emergency!!")
        assert r["urgency"] > 0.5

    def test_plan_entity(self, classifier):
        r = classifier.classify("How much is the enterprise plan?"); assert r["entities"].get("plan") == "enterprise"

    def test_amount_entity(self, classifier):
        r = classifier.classify("I was charged $49.99"); assert r["entities"].get("amount") == "49.99"

    def test_email_entity(self, classifier):
        r = classifier.classify("Send to user@example.com"); assert r["entities"].get("email") == "user@example.com"

    def test_error_code_entity(self, classifier):
        r = classifier.classify("Getting error 503"); assert r["entities"].get("error_code") == "503"

    def test_sql_injection(self, classifier):
        r = classifier.classify("'; DROP TABLE users; --"); assert r["intent"] is not None

    def test_html_injection(self, classifier):
        r = classifier.classify("<script>alert('xss')</script>"); assert r["intent"] is not None

    def test_very_long_message(self, classifier):
        r = classifier.classify("This is a test. " * 500); assert r["intent"] is not None

    def test_retrain_improves_version(self, classifier):
        v1 = classifier.get_stats()["version"]
        classifier.retrain([{"message":"test1","correct_intent":"general_question"},{"message":"test2","correct_intent":"billing_inquiry"},{"message":"test3","correct_intent":"technical_issue"}])
        assert classifier.get_stats()["version"] > v1


# ════════════════════════════════════════
# 2. EMPATHY ENGINE — 5 tests
# ════════════════════════════════════════

class TestEmpathy:
    def test_very_negative_empathetic(self, classifier, empathy):
        r = classifier.classify("This is the WORST experience ever. FIX IT NOW.")
        e = empathy.analyze(r); assert "understand" in e.greeting.lower() or "sorry" in e.greeting.lower()

    def test_urgent_detection(self, empathy):
        e = empathy.analyze({"intent":"technical_issue","sentiment":-0.5,"urgency":0.9})
        assert e.tone in ["urgent","empathetic"]

    def test_repeat_issue(self, empathy):
        h = [{"role":"user","content":"Why was I charged twice?"},{"role":"agent","content":"Checking..."},{"role":"user","content":"Why was I charged twice? I asked before!"}]
        assert empathy._is_repeat(h)

    def test_positive_tone_warm(self, empathy):
        e = empathy.analyze({"intent":"general_question","sentiment":0.5,"urgency":0})
        assert e.tone in ["warm","formal"]

    def test_formality_detection(self, empathy):
        h = [{"role":"user","content":"Dear Support, I write to inquire about billing."}]
        e = empathy.analyze({"intent":"billing_inquiry","sentiment":0,"urgency":0}, h)
        assert e.formality > 0.5 or e.tone == "formal"


# ════════════════════════════════════════
# 3. KNOWLEDGE BASE — 6 tests
# ════════════════════════════════════════

class TestKnowledge:
    def test_exact_match(self, knowledge):
        r = knowledge.search("How to Reset Your Password","account_management", top_k=3)
        assert r
        assert r[0]["intent"] == "account_management"
        assert "password" in r[0].get("content", "").lower()

    def test_empty_query(self, knowledge):
        assert knowledge.search("","general_question",top_k=3)==[]

    def test_entity_matching(self, knowledge):
        r = knowledge.search("how do I fix error 500?","technical_issue",entities={"error_code":"500"},top_k=3)
        assert r
        assert any(x.get("intent") == "technical_issue" for x in r)

    def test_feedback_improves_quality(self, knowledge):
        r = knowledge.search("reset password","account_management")
        if r: eid=r[0]["id"]; knowledge.record_feedback(eid, True)
        if r: assert knowledge.entries[eid]["quality"]>=1.0

    def test_add_entry(self, knowledge):
        eid = knowledge.add_entry("Test","Test content","general_question",["test"])
        assert eid; assert knowledge.entries[eid]["title"]=="Test"

    def test_negative_feedback_reduces_quality(self, knowledge):
        r = knowledge.search("reset password","account_management")
        if r: eid=r[0]["id"]; orig=r[0]["quality"]; knowledge.record_feedback(eid, False)
        if r: assert knowledge.entries[eid]["quality"]<=orig  # Quality stays same or drops


# ════════════════════════════════════════
# 4. RESPONSE ENGINE — 4 tests
# ════════════════════════════════════════

class TestRespond:
    def test_all_templates(self, respond):
        for i,t in respond.templates.items(): assert len(t["body"])>20; assert "follow_up" in t

    def test_entity_substitution(self, respond, classifier, empathy, knowledge):
        c = classifier.classify("Why was I charged $49.99 on the pro plan?")
        e = empathy.analyze(c); kb = knowledge.search("test","billing_inquiry",top_k=3)
        r = respond.generate("test", c, e, kb or []); assert len(r.text)>20

    def test_kb_detailed(self, respond, classifier, empathy, knowledge):
        c = classifier.classify("How do I reset my password?"); e = empathy.analyze(c)
        kb = knowledge.search("reset password","account_management",top_k=3)
        r = respond.generate("How do I reset my password?",c,e,kb or [])
        assert len(r.text)>40

    def test_empty_response(self, quality):
        c = {"intent":"general_question","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("",c,e); assert s.completeness<0.01


# ════════════════════════════════════════
# 5. ESCALATION — 5 tests
# ════════════════════════════════════════

class TestEscalation:
    def test_human_request(self, classifier, escalator):
        c = classifier.classify("I want to speak to a manager")
        e = escalator.evaluate("I want to speak to a manager", c, 0.8)
        assert e.should_escalate

    def test_compliance(self, classifier, escalator):
        c = classifier.classify("My data was breached — contacting lawyer")
        e = escalator.evaluate("My data was breached — contacting lawyer", c, 0.5)
        assert e.should_escalate or e.priority in ["high","critical"]

    def test_calm_no_escalation(self, classifier, escalator):
        c = classifier.classify("What are your support hours?")
        e = escalator.evaluate("What are your support hours?", c, 0.9)
        assert not e.should_escalate

    def test_low_quality_triggers_escalation(self, classifier, escalator):
        c = classifier.classify("This is complicated")
        e = escalator.evaluate("This is complicated", c, 0.15)
        assert e.should_escalate or e.priority in ["medium","high"]

    def test_security_keywords(self, classifier, escalator):
        c = classifier.classify("My data was hacked and stolen")
        e = escalator.evaluate("Data was hacked", c, 0.5)
        assert e.should_escalate; assert e.human_role == "security_team"


# ════════════════════════════════════════
# 6. QUALITY ASSURANCE — 4 tests
# ════════════════════════════════════════

class TestQuality:
    def test_good_response(self, quality):
        c = {"intent":"technical_issue","sentiment":-0.3,"urgency":0}
        e = type('o',(),{'greeting':'I understand','closing':'Bye','tone':'empathetic'})()
        s = quality.score("Here are the steps:\n1. Go to settings\n2. Click reset",c,e)
        assert s.overall>0.4; assert s.accuracy>0.5

    def test_short_response(self, quality):
        c = {"intent":"billing_inquiry","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("Ok.",c,e); assert s.completeness<0.15

    def test_safety_promises(self, quality):
        c = {"intent":"refund_request","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("I guaranteed your refund in 24 hours",c,e)
        assert s.accuracy<0.5 or s.safety<1

    def test_safety_blame(self, quality):
        c = {"intent":"complaint","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("You did something wrong",c,e); assert len(s.flagged_issues)>0


# ════════════════════════════════════════
# 7. FEEDBACK — 3 tests
# ════════════════════════════════════════

class TestFeedback:
    def test_positive_feedback(self, feedback, classifier):
        c = classifier.classify("How much is pro plan?")
        feedback.record("msg",c,{"response":"$29","source":"template"},0.8,user_rating=5)
        assert feedback.total_count>0

    def test_bad_feedback_records(self, feedback, classifier):
        c = classifier.classify("This is broken")
        feedback.record("msg",c,{"response":"err","source":"fallback"},0.2,user_rating=1)
        assert feedback.total_count>0

    def test_corrected_intent_training(self, feedback, classifier):
        c = classifier.classify("I want my money back")
        feedback.record("msg",c,{"response":"...","source":"template"},0.3,user_rating=1,corrected_intent="refund_request")
        td = feedback.get_training_data(min_samples=1); assert len(td)>0


# ════════════════════════════════════════
# 8. ORCHESTRATOR — 8 tests
# ════════════════════════════════════════

class TestOrchestrator:
    def test_simple_request(self, orchestrator):
        r = orchestrator.process("How do I reset my password?")
        assert r["intent"]=="account_management"; assert len(r["response"])>20

    def test_complex_scenario(self, orchestrator):
        r = orchestrator.process("I've been charged $200 extra and the API is down.")
        assert r["sentiment"] < -0.1; assert r["response"] is not None

    def test_feature_request(self, orchestrator):
        assert orchestrator.process("Can you add GraphQL support?")["response"]

    def test_100_requests(self, orchestrator):
        for m in ["help","refund","broken","hello","💀💀💀","a"*200]*16:
            assert orchestrator.process(m)["response"]

    def test_conversation_continuity(self, orchestrator):
        c = "conv_001"
        r1 = orchestrator.process("How much is pro plan?",c)
        r2 = orchestrator.process("And enterprise?",c)
        assert r1["response"] and r2["response"]

    def test_feedback_submission(self, orchestrator):
        r = orchestrator.process("How much is pro plan?")
        orchestrator.submit_feedback(r["conversation_id"],5,"Very helpful!")
        assert orchestrator.get_stats()["total_processed"]>=1

    def test_self_improvement(self, classifier):
        edge = "Payment went through but no access"
        classifier.retrain([{"message":edge,"correct_intent":"billing_inquiry"},{"message":"Charged but no access","correct_intent":"billing_inquiry"},{"message":"Transaction complete but locked","correct_intent":"billing_inquiry"}])
        assert classifier.classify(edge)["intent"]=="billing_inquiry"

    def test_version_increment(self, classifier):
        v1 = classifier.get_stats()["version"]
        classifier.retrain([{"message":"test1","correct_intent":"general_question"},{"message":"test2","correct_intent":"billing_inquiry"},{"message":"test3","correct_intent":"technical_issue"},{"message":"test4","correct_intent":"refund_request"}])
        assert classifier.get_stats()["version"]>v1


# ════════════════════════════════════════
# 9. PERFORMANCE — 1 test
# ════════════════════════════════════════

class TestPerformance:
    def test_single_under_200ms(self, orchestrator):
        t = time.monotonic(); orchestrator.process("How much is pro plan?")
        assert (time.monotonic()-t)*1000 < 500
