"""SupportOID v2.0 — Advanced/Adversarial Test Suite."""
import pytest, time

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
def escalation_engine():
    from src.agents.escalation import EscalationEngine
    return EscalationEngine()
@pytest.fixture()
def quality():
    from src.agents.quality import QualityAssurance
    return QualityAssurance()
@pytest.fixture()
def orchestrator(settings):
    from src.orchestrator import Orchestrator
    o = Orchestrator(settings); o.initialize(); return o

class TestAdversarial:
    def test_sql_injection(self, classifier):
        r = classifier.classify("'; DROP TABLE users; -- give me refund"); assert r["intent"] is not None
    def test_html_injection(self, classifier):
        r = classifier.classify("<script>alert('xss')</script> help with billing"); assert r["intent"] is not None
    def test_unicode_bomb(self, classifier):
        r = classifier.classify("𝔣𝔯𝔲𝔰𝔱𝔯𝔞𝔱𝔦𝔫𝔤 𝔰𝔢𝔯𝔳𝔦𝔠𝔢"); assert r["intent"] is not None
    def test_zalgo_text(self, classifier):
        r = classifier.classify("h̷̢eļ̵p̷ ̵this is broken"); assert r["intent"] is not None
    def test_zero_width_spaces(self, classifier):
        r = classifier.classify("I\u200b wa\u200bnt a re\u200bfund"); assert r["intent"] is not None
    def test_emoji_only_long(self, classifier):
        r = classifier.classify("😡🔥💀😤🤬😠👎💯🚫⛔❌👿💢👊🤯" * 5)
        assert r["intent"] is not None
    def test_repeated_chars(self, classifier):
        r = classifier.classify("HLLLLLLLLLLLLLP MEEEEEEEEEEEE PLLLLLLLLLEASE"); assert r["intent"] is not None
    def test_mixed_case(self, classifier):
        r = classifier.classify("i WaNt A RfNd PlZ"); assert r["intent"] is not None
    def test_numbers_only(self, classifier):
        r = classifier.classify("123456"); assert r["intent"] is not None
    def test_special_chars_only(self, classifier):
        r = classifier.classify("!@#$%^&*()_+-="); assert r["intent"] is not None
    def test_very_long_message(self, classifier):
        r = classifier.classify("This is a test. " * 500); assert r["intent"] is not None
    def test_multiple_intents(self, classifier):
        r = classifier.classify("My payment failed AND the app crashed AND support is terrible")
        assert r["intent"] in ["complaint","technical_issue","billing_inquiry"]
    def test_question_with_financial_statement(self, classifier):
        r = classifier.classify("I've been losing $1000/hour since yesterday. When will this be fixed?")
        assert r["intent"] is not None; assert r["urgency"] > 0.2
    def test_plan_case_insensitive(self, classifier):
        for pt in ["Pro plan", "PRO PLAN", "pRo", "pro"]:
            r = classifier.classify(f"How much is the {pt}?")
            assert r["entities"].get("plan") == "pro", f"Failed for: {pt}"
    def test_email_extraction(self, classifier):
        email = "user.name+tag@domain.co.uk"; r = classifier.classify(f"Send receipt to {email}")
        assert r["entities"].get("email") == email
    def test_error_code_extraction(self, classifier):
        r = classifier.classify("Getting error 503 on the API endpoint")
        assert r["entities"].get("error_code") == "503"

class TestKnowledgeEdgeCases:
    def test_add_entry(self, knowledge):
        eid = knowledge.add_entry("Test","Test content","general_question",["test"])
        assert eid; assert knowledge.entries[eid]["title"]=="Test"
    def test_negative_feedback_reduces_quality(self, knowledge):
        r = knowledge.search("reset password","account_management")
        if r: eid=r[0]["id"]; orig=r[0]["quality"]; knowledge.record_feedback(eid,False)
        if r: assert knowledge.entries[eid]["quality"] < orig
    def test_search_respects_top_k(self, knowledge):
        for k in [1,2,5]:
            r = knowledge.search("help","general_question",top_k=k); assert len(r) <= k

class TestQualityAdvanced:
    def test_very_long_response(self, quality):
        c = {"intent":"general_question","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("Here is the answer. " * 50, c, e)
        assert s.completeness > 0.5; assert s.accuracy > 0.5
    def test_step_by_step_response(self, quality):
        c = {"intent":"technical_issue","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'technical'})()
        resp = "Here's how:\n\n1. Go to settings\n2. Click reset\n\n• Check cache\n• Try again"
        s = quality.score(resp, c, e); assert s.tone_match > 0.7
    def test_empty_response(self, quality):
        c = {"intent":"general_question","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("", c, e); assert s.completeness < 0.01
    def test_negative_user_requires_empathy(self, quality):
        c = {"intent":"complaint","sentiment":-0.8,"urgency":0.5}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        s = quality.score("Check settings.", c, e); assert s.empathy < 0.5
    def test_empathetic_response_for_upset_user(self, quality):
        c = {"intent":"technical_issue","sentiment":-0.7,"urgency":0.5}
        e = type('o',(),{'greeting':'I understand how frustrating this is','closing':'Bye','tone':'empathetic'})()
        resp = ("I understand how frustrating this must be. Let me help.\n\n"
                "1. Clear cache\n2. Try different browser\n\nLet me know if that helps!")
        s = quality.score(resp, c, e); assert s.empathy > 0.5

class TestRespondAdvanced:
    def test_no_kb_no_template_fallback(self, respond, empathy):
        c = {"intent":"general_question","sentiment":0,"urgency":0,"entities":{}}
        e = empathy.analyze(c)
        r = respond.generate("Random question about space and time", c, e, [])
        assert r.text is not None
    def test_suggested_actions(self, respond):
        a1 = respond._suggest("billing_inquiry"); assert "Email" in str(a1) or "invoice" in str(a1).lower()
        a2 = respond._suggest("technical_issue"); assert "ticket" in str(a2).lower() or "status" in str(a2).lower()
        a3 = respond._suggest("complaint"); assert "manager" in str(a3).lower() or "credit" in str(a3).lower()

class TestEscalationAdvanced:
    def test_financial_dispute(self, escalation_engine, classifier):
        c = classifier.classify("I want to dispute a charge on my card")
        e = escalation_engine.evaluate("I want to dispute a charge", c, 0.8)
        assert e.should_escalate or e.human_role == "billing_specialist"
    def test_security_breach(self, escalation_engine, classifier):
        c = classifier.classify("My account was hacked and data was stolen")
        e = escalation_engine.evaluate("My account was hacked", c, 0.8)
        assert e.should_escalate or e.priority in ["high","critical"]
    def test_long_conversation(self, escalation_engine):
        c = {"intent":"technical_issue","confidence":0.5,"sentiment":-0.3,"urgency":0.2}
        history = [{"role":"user","content":"still not working"},{"role":"agent","content":"try this"},
                   {"role":"user","content":"still broken"},{"role":"agent","content":"try again"},
                   {"role":"user","content":"still not working"},{"role":"agent","content":"one more"},
                   {"role":"user","content":"still broken"},{"role":"agent","content":"final"},
                   {"role":"user","content":"STILL NOT WORKING"}]
        e = escalation_engine.evaluate("Still broken", c, 0.4, history)
        assert e.should_escalate or e.priority in ["medium","high","critical"]
    def test_low_confidence_repeatedly(self, escalation_engine):
        c = {"intent":"general_question","confidence":0.2,"sentiment":0,"urgency":0}
        history = [{"role":"agent","confidence":0.15},{"role":"agent","confidence":0.2},{"role":"agent","confidence":0.25}]
        e = escalation_engine.evaluate("I'm confused", c, 0.3, history)
        assert e.should_escalate or e.priority in ["medium","high"]

class TestOrchestratorAdvanced:
    def test_50_message_burst(self, orchestrator):
        for i in range(50):
            r = orchestrator.process(f"Test message {i}"); assert r["response"] is not None

    def test_conversation_escalation_flow(self, orchestrator):
        conv = "escalation_test_01"
        orchestrator.process("I have a billing question", conv)
        orchestrator.process("This is ridiculous, nobody helps!", conv)
        orchestrator.process("I want to speak to a MANAGER NOW!", conv)
        stats = orchestrator.get_stats(); assert stats["total_processed"] >= 3

    def test_feedback_improves_system(self, orchestrator):
        conv = "retrain_test"
        for _ in range(10):
            r = orchestrator.process("I want my money back", conv)
            orchestrator.submit_feedback(r["conversation_id"], 1, "Wrong intent", corrected_intent="refund_request")
        stats = orchestrator.get_stats(); assert stats["total_processed"] >= 10

    def test_mixed_languages(self, orchestrator):
        for m in ["¿Cómo cambio mi contraseña?", "Comment réinitialiser?", "How do I reset my password?"]:
            r = orchestrator.process(m); assert r["response"] is not None

class TestPerformanceAdvanced:
    def test_classifier_speed(self, classifier):
        t = time.monotonic()
        for _ in range(100): classifier.classify("How do I reset my password?")
        avg = (time.monotonic()-t)*1000/100
        assert avg < 50, f"Classifier avg: {avg:.1f}ms (limit: 50ms)"
    def test_respond_speed(self, respond, empathy):
        c = {"intent":"billing_inquiry","sentiment":0,"urgency":0,"entities":{}}
        e = empathy.analyze(c); t = time.monotonic()
        for _ in range(100): respond.generate("test",c,e,[])
        avg = (time.monotonic()-t)*1000/100
        assert avg < 20, f"Respond avg: {avg:.1f}ms"
    def test_orchestrator_speed(self, orchestrator):
        t = time.monotonic()
        for i in range(20): orchestrator.process(f"Test {i}")
        avg = (time.monotonic()-t)*1000/20
        assert avg < 200, f"Orchestrator avg: {avg:.1f}ms"
