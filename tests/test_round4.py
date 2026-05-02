"""Round 4 — Deep integration, concurrency, persistence, edge cases"""
import pytest, time, threading, json, os

@pytest.fixture()
def settings(tmp_path):
    from src.config.settings import Settings
    return Settings(model_dir=str(tmp_path/"models"), kb_dir=str(tmp_path/"knowledge"),
                   feedback_dir=str(tmp_path/"feedback"), training_dir=str(tmp_path/"training"),
                   deployment_profile="test", seed_demo_kb_on_empty=True)
@pytest.fixture()
def classifier(settings):
    from src.agents.classifier import IntentClassifier; return IntentClassifier(settings)
@pytest.fixture()
def empathy():
    from src.agents.empathy import EmpathyEngine; return EmpathyEngine()
@pytest.fixture()
def knowledge(settings):
    from src.agents.knowledge import KnowledgeRetriever; return KnowledgeRetriever(settings.kb_dir, seed_dir=settings.seed_dir, seed_if_empty=True)
@pytest.fixture()
def respond():
    from src.agents.respond import ResponseEngine; return ResponseEngine()
@pytest.fixture()
def escalator():
    from src.agents.escalation import EscalationEngine; return EscalationEngine()
@pytest.fixture()
def quality():
    from src.agents.quality import QualityAssurance; return QualityAssurance()
@pytest.fixture()
def feedback(settings):
    from src.agents.feedback import FeedbackAnalyst; return FeedbackAnalyst(settings)
@pytest.fixture()
def orchestrator(settings):
    from src.orchestrator import Orchestrator
    o = Orchestrator(settings); o.initialize(); return o

# ═════════════════════════════════════════
# REAL-WORLD CONVERSATION FLOWS
# ═════════════════════════════════════════

class TestConversationFlows:
    def test_billing_dispute_escalation(self, orchestrator):
        conv = "billing_dispute"
        r = orchestrator.process("Why was I charged $99? I only have Free.", conv)
        assert r["intent"] == "billing_inquiry"
        r = orchestrator.process("I cancelled last month but was still charged!", conv)
        assert r["response"] is not None
        r = orchestrator.process("I want a FULL refund RIGHT NOW!", conv)
        assert r["response"] is not None
        # Should either escalate or detect refund intent with urgency
        assert r["should_escalate"] or r["intent"] == "refund_request"

    def test_technical_issue_resolution(self, orchestrator):
        conv = "tech_issue"
        r = orchestrator.process("My dashboard shows a blank page.", conv)
        assert r["intent"] in ["technical_issue","bug_report","complaint"]
        r = orchestrator.process("I tried clearing cache, still broken.", conv)
        assert r["response"] is not None
        r = orchestrator.process("Works in incognito now! Thanks!", conv)
        assert r["response"] is not None
        orchestrator.submit_feedback(conv, 4, "Fixed in incognito")

    def test_feature_request_flow(self, orchestrator):
        r = orchestrator.process("Can you add dark mode?")
        assert r["intent"] == "feature_request"
        r = orchestrator.process("Also PDF export please.")
        assert r["response"] is not None

    def test_onboarding_flow(self, orchestrator):
        conv = "onboard"
        r = orchestrator.process("Just signed up. How do I start?", conv)
        assert r["intent"] == "onboarding_help"
        r = orchestrator.process("Invited team. What's next?", conv)
        assert r["response"] is not None
        orchestrator.submit_feedback(conv, 4, "Helpful walkthrough!")

    def test_multi_language(self, orchestrator):
        for msg in ["Hello, help please", "¿Ayuda con mi cuenta?", "Je veux annuler"]:
            r = orchestrator.process(msg)
            assert r["response"] is not None; assert len(r["response"]) > 5

    def test_complaint_to_resolution(self, orchestrator):
        conv = "complaint_fix"
        r = orchestrator.process("This service is TERRIBLE. Nothing works!", conv)
        assert r["intent"] == "complaint"; assert r["sentiment"] < 0
        r = orchestrator.process("Lost 3 clients because of bugs!", conv)
        assert r["should_escalate"] or r["tone"] in ["empathetic","urgent"]
        r = orchestrator.process("Manager called back. Thanks.", conv)
        assert r["response"] is not None
        orchestrator.submit_feedback(conv, 3, "Resolved but frustrating start")

# ═════════════════════════════════════════
# CONCURRENCY & THREAD SAFETY
# ═════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_classifier(self, classifier):
        msgs = ["help","refund","billing","broken"] * 25
        results = [None] * len(msgs)
        def classify(idx, msg): results[idx] = classifier.classify(msg)
        threads = [threading.Thread(target=classify,args=(i,m)) for i,m in enumerate(msgs)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(r is not None and r["intent"] is not None for r in results)

    def test_concurrent_knowledge_search(self, knowledge):
        queries = ["help","billing","error","password","plan"] * 20
        results = [None] * len(queries)
        def search(idx, q): results[idx] = knowledge.search(q, "general_question", top_k=3)
        threads = [threading.Thread(target=search,args=(i,q)) for i,q in enumerate(queries)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(isinstance(r, list) for r in results)

    def test_concurrent_feedback(self, feedback):
        def record(rating):
            feedback.record("msg", {}, {"response":"r","source":"t"}, quality_score=0.5, user_rating=rating)
        threads = [threading.Thread(target=record,args=(i%5+1,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert feedback.total_count == 50

    def test_concurrent_orchestrator(self, orchestrator):
        msgs = ["Help","Billing?","Error 500","Refund","Feature","Password"] * 16
        results = [None] * len(msgs)
        def process(idx, msg): results[idx] = orchestrator.process(msg)
        threads = [threading.Thread(target=process,args=(i,m)) for i,m in enumerate(msgs)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(r is not None and r["response"] is not None for r in results)

# ═════════════════════════════════════════
# PERSISTENCE & RECOVERY
# ═════════════════════════════════════════

class TestKnowledgePersistence:
    def test_save_and_reload(self, settings, knowledge):
        orig = len(knowledge.entries)
        knowledge.add_entry("test-persist","Persisted content","general_question",["test"])
        assert len(knowledge.entries) == orig + 1
        new_kb = __import__("src.agents.knowledge",fromlist=["KnowledgeRetriever"]).KnowledgeRetriever(
            settings.kb_dir,
            seed_dir=settings.seed_dir,
            seed_if_empty=True,
        )
        assert len(new_kb.entries) >= orig + 1

    def test_large_kb_performance(self, settings, knowledge):
        for i in range(500):
            knowledge.add_entry(f"e-{i}", f"Content {i}", "general_question", [f"t{i}"])
        assert len(knowledge.entries) >= 507
        t = time.monotonic()
        results = knowledge.search("test search query", "general_question", top_k=10)
        elapsed = (time.monotonic()-t)*1000
        assert elapsed < 500; assert len(results) <= 10

    def test_quality_propagation(self, knowledge):
        r = knowledge.search("reset password","account_management",top_k=2)
        if len(r) >= 2:
            eid1, eid2 = r[0]["id"], r[1]["id"]
            for _ in range(3): knowledge.record_feedback(eid1, True)
            for _ in range(3): knowledge.record_feedback(eid2, False)
            r2 = knowledge.search("reset password","account_management",top_k=3)
            assert r2[0]["id"] == eid1

# ═════════════════════════════════════════
# ERROR HANDLING & EDGE CASES
# ═════════════════════════════════════════

class TestErrorHandling:
    def test_extreme_inputs(self, classifier):
        for inp in [" ","\n\n\n","🔥"*1000,"a"*10000,json.dumps({"k":"v"})*100,"\x00\x01"*100]:
            r = classifier.classify(inp)
            assert r is not None; assert "intent" in r; assert 0 <= r["confidence"] <= 1

    def test_respond_edge_cases(self, respond, empathy):
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        c = {"intent":"general_question","sentiment":0,"urgency":0,"entities":{}}
        for kb in [None, [], [{"content":"test"}]]:
            r = respond.generate("test", c, e, kb or [])
            assert r.text is not None; assert len(r.text) > 0

    def test_quality_edge_cases(self, quality):
        c = {"intent":"general_question","sentiment":0,"urgency":0}
        e = type('o',(),{'greeting':'Hi','closing':'Bye','tone':'warm'})()
        for resp in [" ","\n\n","a"*1000,"😊😊😊","I don't know","Try again later",""]:
            s = quality.score(resp, c, e); assert 0 <= s.overall <= 1

# ═════════════════════════════════════════
# RETRAINING EDGE CASES
# ═════════════════════════════════════════

class TestRetrainingEdgeCases:
    def test_single_intent_retrain(self, classifier):
        result = classifier.retrain([
            {"message":"test1","correct_intent":"general_question"},
            {"message":"test2","correct_intent":"general_question"},
            {"message":"test3","correct_intent":"general_question"},
        ])
        assert result.get("status") == "skipped" or result.get("version", 0) > 1

    def test_typos_retrain(self, classifier):
        result = classifier.retrain([
            {"message":"hlp pls","correct_intent":"general_question"},
            {"message":"biling qestion","correct_intent":"billing_inquiry"},
            {"message":"techncal issu","correct_intent":"technical_issue"},
            {"message":"refnd please","correct_intent":"refund_request"},
            {"message":"acount help","correct_intent":"account_management"},
        ])
        assert result.get("status") != "skipped" or result.get("version", 0) > 1

    def test_multiple_retrain_cycles(self, classifier):
        v1 = classifier.get_stats()["version"]
        for cycle in range(3):
            classifier.retrain([
                {"message":f"cycle{cycle} msg1","correct_intent":"general_question"},
                {"message":f"cycle{cycle} msg2","correct_intent":"billing_inquiry"},
                {"message":f"cycle{cycle} msg3","correct_intent":"technical_issue"},
            ])
        assert classifier.get_stats()["version"] >= v1

# ═════════════════════════════════════════
# STRESS TESTS
# ═════════════════════════════════════════

class TestStress:
    def test_500_messages(self, orchestrator):
        for i in range(500):
            r = orchestrator.process(f"Message {i}")
            assert r["response"] is not None

    def test_long_conversation(self, orchestrator):
        conv = "long_conv"
        for i in range(30):
            r = orchestrator.process(f"Question #{i} about {['billing','tech','feature','refund'][i%4]}", conv)
            assert r["response"] is not None

    def test_rapid_intent_switching(self, orchestrator):
        for topic in ["I want refund","How reset password?","App crashing!","Add dark mode?","Support hours?"]:
            r = orchestrator.process(topic)
            assert r["response"] is not None; assert r["intent"] is not None

    def test_memory_efficiency_2000(self, orchestrator):
        t = time.monotonic()
        for i in range(2000):
            orchestrator.process(f"Msg {i}")
        avg = (time.monotonic()-t)*1000/2000
        assert avg < 100, f"2000 msgs avg: {avg:.0f}ms"

    def test_response_time_p95(self, orchestrator):
        times = []
        for i in range(100):
            t = time.monotonic(); orchestrator.process(f"Test {i}"); times.append((time.monotonic()-t)*1000)
        times.sort(); p95 = times[int(len(times)*0.95)]
        assert p95 < 150, f"P95: {p95:.0f}ms"
