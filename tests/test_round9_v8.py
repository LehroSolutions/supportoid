"""
SupportOID v8.0 — Test Suite for New Features
===============================================
Tests for:
  1. Advanced RAG Retrieval (BM25, TF-IDF, N-gram, hybrid scoring)
  2. Self-Learning Engine (auto KB creation, pattern detection, recalibration)
  3. Knowledge Base Quality Scoring (5 dimensions, gap analysis)
  4. Trace Summarization (single + multi-session)
  5. Supported web interface verification
  6. Integration tests (end-to-end pipeline with new agents)
"""

import pytest
import json
import os
import sys
import math

# ── Fixtures ──

SAMPLE_ENTRIES = {
    "kb-001": {
        "id": "kb-001",
        "title": "How to Reset Your Password",
        "content": "Go to login page, click Forgot Password, enter your email address. Check your inbox and click the reset link. The link expires in 24 hours. If you don't receive the email, check your spam folder or contact support.",
        "intent": "account_management",
        "tags": ["password", "reset", "login", "account"],
        "quality": 0.9,
        "usage": 15,
    },
    "kb-002": {
        "id": "kb-002",
        "title": "Billing & Payment FAQ",
        "content": "Billing starts on signup date. View billing info under Settings > Billing. We accept credit cards, PayPal, and wire transfers for Enterprise plans. Invoices are sent automatically at the start of each billing cycle.",
        "intent": "billing_inquiry",
        "tags": ["billing", "payment", "subscription", "invoice"],
        "quality": 0.8,
        "usage": 8,
    },
    "kb-003": {
        "id": "kb-003",
        "title": "Refund Policy",
        "content": "30-day money-back guarantee on all plans. Request refund via Settings > Billing > Refund Request. Processing takes 5-10 business days. Annual plans are prorated.",
        "intent": "refund_request",
        "tags": ["refund", "money-back", "cancellation"],
        "quality": 0.7,
        "usage": 5,
    },
    "kb-004": {
        "id": "kb-004",
        "title": "Troubleshooting Error 500",
        "content": "Check status.lehrosolutions.tech for known outages. Retry in 2-3 minutes. Clear your browser cache. Try a different browser. Common causes: database timeout, third-party API failure. Error 500 means a server-side issue.",
        "intent": "technical_issue",
        "tags": ["error", "500", "troubleshooting", "server"],
        "quality": 0.85,
        "usage": 12,
    },
}


@pytest.fixture()
def rag_retriever():
    from src.agents.rag_retrieval import RAGRetriever
    return RAGRetriever(SAMPLE_ENTRIES)


@pytest.fixture()
def tmp_kb_dir(tmp_path):
    """Create a temporary KB directory with sample entries."""
    kb_dir = tmp_path / "knowledge"
    kb_dir.mkdir()
    for eid, entry in SAMPLE_ENTRIES.items():
        with open(kb_dir / f"{eid}.json", "w") as f:
            json.dump(entry, f)
    return kb_dir


@pytest.fixture()
def tmp_feedback_dir(tmp_path):
    """Create a temporary feedback directory."""
    fb_dir = tmp_path / "feedback"
    fb_dir.mkdir()
    # Write sample feedback
    today = "2026-04-04"
    entries = [
        {"id": "fb_0", "timestamp": "2026-04-04T10:00:00", "message_preview": "How do I reset password?",
         "predicted_intent": "account_management", "confidence": 0.94, "sentiment": 0,
         "response": "Go to login and click Forgot Password.", "response_source": "knowledge",
         "quality_score": 0.9, "user_rating": 5, "auto_action": "none"},
        {"id": "fb_1", "timestamp": "2026-04-04T11:00:00", "message_preview": "I want refund pls",
         "predicted_intent": "refund_request", "confidence": 0.89, "sentiment": -0.3,
         "response": "30-day guarantee applies.", "response_source": "knowledge",
         "quality_score": 0.6, "user_rating": 2, "corrected_intent": "refund_request",
         "auto_action": "add_to_training"},
        {"id": "fb_2", "timestamp": "2026-04-04T12:00:00", "message_preview": "refund my money now",
         "predicted_intent": "refund_request", "confidence": 0.72, "sentiment": -0.7,
         "response": "Contact support.", "response_source": "llm",
         "quality_score": 0.3, "user_rating": 1, "auto_action": "flag_for_review"},
        {"id": "fb_3", "timestamp": "2026-04-04T13:00:00", "message_preview": "Need refund for order",
         "predicted_intent": "refund_request", "confidence": 0.85, "sentiment": -0.2,
         "response": "See refund policy.", "response_source": "knowledge",
         "quality_score": 0.5, "user_rating": 2, "auto_action": "needs_improvement"},
    ]
    path = fb_dir / f"feedback-{today}.jsonl"
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return fb_dir


# ═══════════════════════════════════════════
# 1. RAG RETRIEVAL TESTS
# ═══════════════════════════════════════════

class TestTokenize:
    def test_basic_tokenization(self):
        from src.agents.rag_retrieval import tokenize
        tokens = tokenize("How to reset my password please")
        assert "reset" in tokens
        assert "password" in tokens
        assert "please" in tokens
        assert "to" not in tokens  # stop word
        assert "my" not in tokens  # stop word

    def test_empty_text(self):
        from src.agents.rag_retrieval import tokenize
        assert tokenize("") == []
        assert tokenize("   ") == []

    def test_punctuation_handling(self):
        from src.agents.rag_retrieval import tokenize
        tokens = tokenize("Hello, world! How are you?")
        assert "hello" in tokens
        assert "world" in tokens

    def test_case_insensitive(self):
        from src.agents.rag_retrieval import tokenize
        assert tokenize("Hello") == tokenize("hello")


class TestIDF:
    def test_idf_basic(self):
        from src.agents.rag_retrieval import compute_idf
        docs = ["password reset login", "billing payment", "password billing"]
        idf = compute_idf(docs)
        assert "password" in idf
        assert "billing" in idf
        # password appears in 2/3 docs, less unique than "reset" in 1/3
        assert idf["reset"] > idf["password"]

    def test_idf_empty(self):
        from src.agents.rag_retrieval import compute_idf
        assert compute_idf([]) == {}


class TestBM25:
    def test_bm25_perfect_match(self):
        from src.agents.rag_retrieval import compute_bm25
        score = compute_bm25("password reset", "How to password reset your account", avg_dl=5.0)
        assert score > 0

    def test_bm25_no_match(self):
        from src.agents.rag_retrieval import compute_bm25
        score = compute_bm25("shipping delivery", "billing and payment", avg_dl=5.0)
        assert score == pytest.approx(0, abs=0.5)  # very low

    def test_bm25_partial_match(self):
        from src.agents.rag_retrieval import compute_bm25
        s1 = compute_bm25("password reset", "password reset", avg_dl=5.0)
        s2 = compute_bm25("password reset", "just password", avg_dl=5.0)
        assert s1 > s2


class TestCosineSimilarity:
    def test_identical_vectors(self):
        from src.agents.rag_retrieval import cosine_similarity
        vec = {"a": 1.0, "b": 2.0}
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from src.agents.rag_retrieval import cosine_similarity
        assert cosine_similarity({"a": 1.0}, {"b": 1.0}) == pytest.approx(0.0)

    def test_empty_vectors(self):
        from src.agents.rag_retrieval import cosine_similarity
        assert cosine_similarity({}, {}) == pytest.approx(0.0)

    def test_partial_overlap(self):
        from src.agents.rag_retrieval import cosine_similarity
        a = {"a": 1.0, "b": 1.0}
        b = {"a": 1.0, "c": 1.0}
        sim = cosine_similarity(a, b)
        assert 0 < sim < 1


class TestNgramOverlap:
    def test_identical_strings(self):
        from src.agents.rag_retrieval import ngram_overlap
        assert ngram_overlap("hello", "hello") == pytest.approx(1.0)

    def test_completely_different(self):
        from src.agents.rag_retrieval import ngram_overlap
        score = ngram_overlap("abcdef", "xyz")
        assert score == 0

    def test_partial_overlap(self):
        from src.agents.rag_retrieval import ngram_overlap
        score = ngram_overlap("hello world", "hello there")
        assert 0 < score < 1

    def test_short_strings(self):
        from src.agents.rag_retrieval import ngram_overlap
        # "ab" is only 2 chars, need 3-grams → no ngrams possible
        score = ngram_overlap("ab", "cd")
        assert score == 0


class TestRAGRetriever:
    def test_search_basic(self, rag_retriever):
        results = rag_retriever.search("password reset", intent="account_management", top_k=3)
        assert len(results) > 0
        assert results[0]["id"] == "kb-001"  # Most relevant for "password reset"

    def test_search_empty_query(self, rag_retriever):
        results = rag_retriever.search("", intent="")
        assert results == []

    def test_search_returns_scores(self, rag_retriever):
        results = rag_retriever.search("billing", top_k=5)
        for r in results:
            assert "_score" in r
            assert "_bm25" in r
            assert "_tfidf" in r
            assert "_ngram" in r

    def test_search_intent_boost(self, rag_retriever):
        r1 = rag_retriever.search("billing", intent="billing_inquiry", top_k=1)
        r2 = rag_retriever.search("billing", intent="account_management", top_k=1)
        assert r1[0]["_score"] >= r2[0]["_score"]

    def test_search_entity_boost(self, rag_retriever):
        results = rag_retriever.search("payment", intent="billing_inquiry",
                                        entities={"plan": "Enterprise"}, top_k=3)
        assert len(results) > 0

    def test_search_top_k_limit(self, rag_retriever):
        results = rag_retriever.search("the", top_k=1)
        assert len(results) <= 1

    def test_search_with_recency(self, rag_retriever):
        results = rag_retriever.search_with_recency("password", top_k=3)
        assert len(results) > 0
        assert results[0]["_score"] > 0

    def test_custom_weights(self, rag_retriever):
        weights = {"bm25": 0.8, "tfidf": 0.1, "ngram": 0.05, "intent": 0.03, "entity": 0.02}
        results = rag_retriever.search("password", top_k=2, weights=weights)
        assert len(results) > 0

    def test_bm25_scores_in_results(self, rag_retriever):
        results = rag_retriever.search("reset", top_k=3)
        assert len(results) > 0
        # With no intent specified, _intent_match should be False (correct behavior)
        assert results[0].get("_intent_match", False) == False
        # With matching intent, it should be True
        results_with_intent = rag_retriever.search("reset", intent="account_management", top_k=3)
        assert results_with_intent[0].get("_intent_match", False) == True

    def test_all_results_have_entry_fields(self, rag_retriever):
        results = rag_retriever.search("billing", top_k=3)
        for r in results:
            assert "id" in r
            assert "title" in r
            assert "content" in r
            assert "tags" in r


# ═══════════════════════════════════════════
# 2. SELF-LEARNING ENGINE TESTS
# ═══════════════════════════════════════════

class TestSelfLearning:
    def test_init(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        assert engine is not None

    def test_load_feedback(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        entries = engine.load_feedback_entries(days=30)
        assert len(entries) == 4

    def test_analyze_patterns_empty(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        result = engine.analyze_feedback_patterns([])
        assert result["total_analyzed"] == 0

    def test_analyze_patterns_with_data(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        entries = engine.load_feedback_entries(days=30)
        result = engine.analyze_feedback_patterns(entries)
        assert result["total_analyzed"] == 4
        assert "low_rated_count" in result
        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

    def test_recalibrate_quality(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        entries = engine.load_feedback_entries(days=30)
        recalibrated = engine.recalibrate_quality_scores(entries)
        assert isinstance(recalibrated, dict)

    def test_generate_recommendations(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        entries = engine.load_feedback_entries(days=30)
        result = engine.analyze_feedback_patterns(entries)
        assert len(result["recommendations"]) >= 1

    def test_learning_log(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        engine._log_learning("test_action", {"detail": "test"})
        assert len(engine.learning_log) == 1
        assert engine.learning_log[0]["action"] == "test_action"

    def test_learning_report(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        report = engine.get_learning_report()
        assert "total_learning_actions" in report
        assert "auto_kb_entries_created" in report

    def test_extract_common_terms(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        from src.agents.self_learning import SelfLearningEngine
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(tmp_path / "training")
        )
        terms = engine._extract_common_terms([
            "How do I reset my password",
            "I need to reset my password",
            "Can you help me reset password",
        ])
        assert "reset" in terms
        assert "password" in terms


# ═══════════════════════════════════════════
# 3. KB QUALITY SCORING TESTS
# ═══════════════════════════════════════════

class TestKBQuality:
    def test_init(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        assert len(scorer.entries) == 4

    def test_score_single(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        entry = scorer.entries["kb-001"]
        scores = scorer.score_single(entry)
        assert "entry_id" in scores
        assert "dimensions" in scores
        assert "overall" in scores
        assert "grade" in scores
        assert "recommendations" in scores
        assert 0 <= scores["overall"] <= 1

    def test_score_all(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        report = scorer.score_all()
        assert "total_entries" in report
        assert report["total_entries"] == 4
        assert "overall_avg" in report
        assert "grade_distribution" in report
        assert "dimension_averages" in report

    def test_score_all_empty(self, tmp_path):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_path / "empty_kb"))
        report = scorer.score_all()
        assert report["total_entries"] == 0

    def test_grade_distribution(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        report = scorer.score_all()
        grades = report["grade_distribution"]
        assert sum(grades.values()) == 4
        for g in grades:
            assert g in ("A", "B", "C", "D", "F")

    def test_coverage_gaps(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        gaps = scorer.find_coverage_gaps([
            "account_management", "billing_inquiry", "refund_request",
            "technical_issue", "complaint", "feature_request"
        ])
        # complaint and feature_request have no KB entries
        gap_intents = [g["intent"] for g in gaps]
        assert "complaint" in gap_intents
        assert "feature_request" in gap_intents

    def test_completeness_score_actionable(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        # kb-001 has actionable language ("Go to", "click")
        entry = scorer.entries["kb-001"]
        comp = scorer._score_completeness(entry)
        assert comp > 0.5  # Good actionable content

    def test_freshness_score(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        entry = scorer.entries["kb-001"]
        freshness = scorer._score_usage(entry)
        assert 0 <= freshness <= 1

    def test_grade_mapping(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        assert scorer._grade(0.95) == "A"
        assert scorer._grade(0.80) == "B"
        assert scorer._grade(0.60) == "C"
        assert scorer._grade(0.45) == "D"
        assert scorer._grade(0.30) == "F"

    def test_recommendations_present(self, tmp_kb_dir):
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))
        entry = scorer.entries["kb-001"]
        scores = scorer.score_single(entry)
        assert len(scores["recommendations"]) > 0


# ═══════════════════════════════════════════
# 4. TRACE SUMMARIZATION TESTS
# ═══════════════════════════════════════════

class TestTraceSummary:
    def test_summarize_single_basic(self):
        from src.agents.trace_summary import summarize_single_trace
        trace = {
            "session_id": "test_1",
            "user_input": "How do I reset my password?",
            "duration_s": 0.042,
            "steps": [
                {"agent": "Classifier", "action": "classify", "status": "success", "duration_ms": 30},
                {"agent": "Empathy", "action": "analyze", "status": "success", "duration_ms": 5},
                {"agent": "Knowledge", "action": "retrieve", "status": "success", "duration_ms": 20},
            ],
            "model": "qwen3.6",
            "cost": 0.004,
            "tokens": 1240,
        }
        summary = summarize_single_trace(trace)
        assert summary["session_id"] == "test_1"
        assert "summary" in summary
        assert summary["total_steps"] == 3
        assert summary["escalated"] is False
        assert summary["has_error"] is False

    def test_summarize_escalated(self):
        from src.agents.trace_summary import summarize_single_trace
        trace = {
            "session_id": "test_escalation",
            "user_input": "I want to speak to your manager right now",
            "duration_s": 0.080,
            "steps": [
                {"agent": "Classifier", "action": "classify", "status": "success", "duration_ms": 40},
                {"agent": "Escalation", "action": "human handoff", "status": "success", "duration_ms": 10},
            ],
            "error": "escalated",
        }
        summary = summarize_single_trace(trace)
        assert summary["escalated"] is True
        assert "escalat" in summary["summary"].lower() or "Escalated" in summary["summary"]

    def test_summarize_with_error(self):
        from src.agents.trace_summary import summarize_single_trace
        trace = {
            "session_id": "test_error",
            "user_input": "test",
            "duration_s": 0.010,
            "steps": [{"agent": "Classifier", "action": "classify", "status": "error", "duration_ms": 5}],
            "error": "timeout",
        }
        summary = summarize_single_trace(trace)
        assert summary["has_error"] is True

    def test_summarize_quality_warning(self):
        from src.agents.trace_summary import summarize_single_trace
        trace = {
            "session_id": "test_warn",
            "user_input": "test",
            "duration_s": 0.010,
            "steps": [
                {"agent": "Quality", "action": "score", "status": "warning", "duration_ms": 3, "reason": "low empathy"}
            ],
        }
        summary = summarize_single_trace(trace)
        assert summary["has_warnings"] is True

    def test_summarize_multiple_traces(self):
        from src.agents.trace_summary import summarize_multiple_traces
        traces = [
            {"session_id": "t1", "user_input": "hello", "duration_s": 0.01,
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 5}]},
            {"session_id": "t2", "user_input": "bye", "duration_s": 0.02,
             "steps": [{"agent": "B", "action": "y", "status": "success", "duration_ms": 10}],
             "model": "sonnet", "cost": 0.01, "tokens": 500},
        ]
        report = summarize_multiple_traces(traces)
        assert report["total_sessions"] == 2
        assert report["healthy_rate"] == 100.0
        assert report["avg_duration_s"] == pytest.approx(0.015)
        assert "executive_summary" in report
        assert "agent_workload" in report

    def test_summarize_multiple_empty(self):
        from src.agents.trace_summary import summarize_multiple_traces
        report = summarize_multiple_traces([])
        assert report["total_sessions"] == 0

    def test_executive_summary_healthy(self):
        from src.agents.trace_summary import summarize_multiple_traces
        traces = [{"session_id": f"t{i}", "user_input": "test", "duration_s": 0.01,
                   "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 5}]}
                  for i in range(10)]
        report = summarize_multiple_traces(traces)
        assert "Excellent" in report["executive_summary"]

    def test_executive_summary_mixed(self):
        from src.agents.trace_summary import summarize_multiple_traces
        traces = [
            {"session_id": f"t{i}", "user_input": "test", "duration_s": 0.01,
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 5}]}
            for i in range(6)
        ] + [{"session_id": "bad", "user_input": "angry", "duration_s": 0.1,
              "steps": [{"agent": "Escalation", "action": "human handoff", "status": "success", "duration_ms": 20}],
              "error": "escalated"}]
        report = summarize_multiple_traces(traces)
        assert report["escalations"] >= 1
        assert report["health_rate" if "health_rate" in report else "healthy_rate"] < 100

    def test_slowest_sessions_sorted(self):
        from src.agents.trace_summary import summarize_multiple_traces
        traces = [
            {"session_id": f"t{i}", "user_input": "test", "duration_s": 0.01 * (i+1),
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": i*5}]}
            for i in range(10)
        ]
        report = summarize_multiple_traces(traces)
        slowest = report["slowest_sessions"]
        assert len(slowest) <= 5
        for i in range(len(slowest) - 1):
            assert slowest[i]["duration_s"] >= slowest[i+1]["duration_s"]

    def test_model_distribution(self):
        from src.agents.trace_summary import summarize_multiple_traces
        traces = [
            {"session_id": "t1", "user_input": "a", "duration_s": 0.01,
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 5}],
             "model": "qwen3.6"},
            {"session_id": "t2", "user_input": "b", "duration_s": 0.02,
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 10}],
             "model": "sonnet"},
            {"session_id": "t3", "user_input": "c", "duration_s": 0.015,
             "steps": [{"agent": "A", "action": "x", "status": "success", "duration_ms": 7}],
             "model": "qwen3.6"},
        ]
        report = summarize_multiple_traces(traces)
        assert report["model_distribution"]["qwen3.6"] == 2
        assert report["model_distribution"]["sonnet"] == 1


# ═══════════════════════════════════════════
# 5. SUPPORTED WEB INTERFACE TESTS
# ═══════════════════════════════════════════

class TestSupportedWebInterface:
    def test_public_interface_exports_router(self):
        from src.interface import web_router
        assert web_router is not None

    def test_supported_routes_present(self):
        from src.interface.web_routes import router
        route_paths = {route.path for route in router.routes}
        assert "/" in route_paths
        assert "/login" in route_paths
        assert "/dashboard" in route_paths
        assert "/chat" in route_paths
        assert "/traces" in route_paths
        assert "/kb-quality" in route_paths
        assert "/analytics" in route_paths
        assert "/api/me" in route_paths

    def test_frontend_dist_location_points_to_react_bundle(self):
        from src.interface.web_routes import FRONTEND_DIST
        assert FRONTEND_DIST.name == "dist"
        assert FRONTEND_DIST.parent.name == "frontend"

    def test_template_fallbacks_exist(self):
        templates_dir = os.path.join("src", "interface", "templates")
        assert os.path.exists(os.path.join(templates_dir, "login.html"))
        assert os.path.exists(os.path.join(templates_dir, "dashboard.html"))
        assert os.path.exists(os.path.join(templates_dir, "chat.html"))
        assert os.path.exists(os.path.join(templates_dir, "traces.html"))
        assert os.path.exists(os.path.join(templates_dir, "kb_quality.html"))
        assert os.path.exists(os.path.join(templates_dir, "analytics.html"))


# ═══════════════════════════════════════════
# 6. INTEGRATION TESTS
# ═══════════════════════════════════════════

class TestIntegration:
    def test_rag_and_kb_quality(self, rag_retriever, tmp_kb_dir):
        """Test that RAG results can be quality-scored."""
        from src.agents.kb_quality import KBQualityScorer
        scorer = KBQualityScorer(kb_dir=str(tmp_kb_dir))

        # Search with RAG
        results = rag_retriever.search("password", top_k=2)
        assert len(results) > 0

        # Score top result
        top = results[0]
        scores = scorer.score_single(top)
        assert scores["overall"] > 0

    def test_rag_and_trace_summary(self, rag_retriever):
        """Test that RAG scores appear in trace summaries."""
        from src.agents.trace_summary import summarize_single_trace
        trace = {
            "session_id": "int_test_1",
            "user_input": "password reset",
            "duration_s": 0.050,
            "steps": [
                {"agent": "Classifier", "action": "classify", "status": "success", "duration_ms": 30},
                {"agent": "RAG Engine", "action": "BM25+TF-IDF+N-gram", "status": "success",
                 "duration_ms": 15, "bm25": 1.24, "tfidf": 0.82, "ngram": 0.31},
                {"agent": "Response", "action": "generate", "status": "success", "duration_ms": 40},
            ],
        }
        summary = summarize_single_trace(trace)
        assert summary["total_steps"] == 3
        assert "agent_breakdown" in summary
        assert summary["agent_breakdown"].get("RAG Engine") == 1

    def test_self_learning_creates_log(self, tmp_feedback_dir, tmp_kb_dir, tmp_path):
        """Test that self-learning writes to the training directory."""
        from src.agents.self_learning import SelfLearningEngine
        train_dir = tmp_path / "training"
        train_dir.mkdir()
        engine = SelfLearningEngine(
            feedback_dir=str(tmp_feedback_dir),
            kb_dir=str(tmp_kb_dir),
            training_dir=str(train_dir)
        )
        engine._log_learning("test", {"key": "value"})

        log_file = train_dir / "learning_log.jsonl"
        assert log_file.exists()

    def test_rag_hybrid_vs_baseline_comparison(self, tmp_path):
        """Verify the knowledge retriever still works alongside RAG retriever."""
        from src.agents.knowledge import KnowledgeRetriever
        from src.agents.rag_retrieval import RAGRetriever
        import os

        kb_dir = tmp_path / "baseline_kb"
        kb_dir.mkdir()
        entries = {
            "kb-001": {"id": "kb-001", "title": "Reset Password",
                       "content": "Go to login and click forgot password.",
                       "intent": "account_management", "tags": ["password", "reset"],
                       "quality": 0.9, "usage": 15}
        }
        for eid, entry in entries.items():
            with open(os.path.join(str(kb_dir), f"{eid}.json"), "w") as f:
                json.dump(entry, f)

        # Baseline
        kr = KnowledgeRetriever(str(kb_dir))
        base_results = kr.search("password reset", "account_management", top_k=1)

        # Advanced RAG
        rr = RAGRetriever(entries)
        rag_results = rr.search("password reset", intent="account_management", top_k=1)

        # Both should return the same entry
        assert len(base_results) > 0
        assert len(rag_results) > 0
        assert base_results[0]["id"] == rag_results[0]["id"]

    def test_full_pipeline_with_new_agents(self, tmp_path):
        """Test that the enhanced orchestrator still works with existing tests."""
        from src.config.settings import Settings
        settings = Settings(
            model_dir=str(tmp_path / "models"),
            kb_dir=str(tmp_path / "knowledge"),
            feedback_dir=str(tmp_path / "feedback"),
            training_dir=str(tmp_path / "training"),
            deployment_profile="test",
            seed_demo_kb_on_empty=True,
        )
        from src.orchestrator import Orchestrator
        orch = Orchestrator(settings)
        orch.initialize()

        result = orch.process("How do I reset my password?")
        assert result["response"] is not None
        assert result["intent"] is not None
        assert result["confidence"] > 0


# ═══════════════════════════════════════════
# 7. NEW MODULES IMPORT CHECK
# ═══════════════════════════════════════════

class TestImports:
    def test_rag_retrieval_imports(self):
        from src.agents import rag_retrieval
        assert hasattr(rag_retrieval, 'RAGRetriever')
        assert hasattr(rag_retrieval, 'compute_bm25')
        assert hasattr(rag_retrieval, 'compute_idf')
        assert hasattr(rag_retrieval, 'cosine_similarity')
        assert hasattr(rag_retrieval, 'ngram_overlap')
        assert hasattr(rag_retrieval, 'tokenize')

    def test_self_learning_imports(self):
        from src.agents import self_learning
        assert hasattr(self_learning, 'SelfLearningEngine')

    def test_kb_quality_imports(self):
        from src.agents import kb_quality
        assert hasattr(kb_quality, 'KBQualityScorer')

    def test_trace_summary_imports(self):
        from src.agents import trace_summary
        assert hasattr(trace_summary, 'summarize_single_trace')
        assert hasattr(trace_summary, 'summarize_multiple_traces')
        assert hasattr(trace_summary, 'generate_trace_summary_file')

    def test_interface_exports_web_router(self):
        from src.interface import web_router
        assert web_router is not None
