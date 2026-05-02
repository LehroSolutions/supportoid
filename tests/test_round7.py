"""Tests for Hour 2 features:
  1) NVIDIA PersonaPlex as model provider
  2) Multi-model fallback chain
  3) Cost tracking per conversation
  4) Model comparison dashboard in CLI
  5) Voice output support
"""
import pytest, time, json, sys, asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# -- 1) NVIDIA PersonaPlex as model provider --

class TestPersonaPlexProvider:
    def test_personaplex_in_default_models(self):
        from src.agents.model_router import DEFAULT_MODELS
        providers = [m["provider"] for m in DEFAULT_MODELS]
        assert "nvidia" in providers

    def test_personaplex_model_config(self):
        from src.agents.model_router import DEFAULT_MODELS
        pp = next((m for m in DEFAULT_MODELS if m["provider"] == "nvidia"), None)
        assert pp is not None
        assert pp["name"] == "nvidia-personaplex"
        assert pp["model_id"] == "nvidia/personaplex-7b-v1"
        assert "voice" in pp["capabilities"]
        assert "persona" in pp["capabilities"]
        assert "chat" in pp["capabilities"]

    def test_personaplex_integration_class_exists(self):
        from src.agents.personaplex_integration import PersonaPlexIntegration
        pp = PersonaPlexIntegration(mode="nim")
        assert pp.mode == "nim"
        assert not pp.is_available()

    def test_personaplex_local_not_available(self):
        from src.agents.personaplex_integration import PersonaPlexIntegration
        pp = PersonaPlexIntegration(mode="local")
        assert pp.local_endpoint == "http://localhost:8080"
        assert not pp.is_available()

    def test_personas_defined(self):
        from src.agents.personaplex_integration import PersonaPlexIntegration
        assert "support" in PersonaPlexIntegration.AGENT_PERSONAS
        assert "technical" in PersonaPlexIntegration.AGENT_PERSONAS
        assert "friendly" in PersonaPlexIntegration.AGENT_PERSONAS


# -- 2) Multi-model fallback chain --

class TestFallbackChain:
    def test_chain_created(self):
        from src.agents.model_router import FallbackChain, DEFAULT_MODELS
        fc = FallbackChain("qwen3.6-free", DEFAULT_MODELS)
        chain = fc.chain()
        assert chain[0] == "qwen3.6-free"
        assert len(chain) > 1

    def test_primary_first(self):
        from src.agents.model_router import FallbackChain, DEFAULT_MODELS
        fc = FallbackChain("claude-sonnet", DEFAULT_MODELS)
        assert fc.chain()[0] == "claude-sonnet"

    def test_next_after(self):
        from src.agents.model_router import FallbackChain, DEFAULT_MODELS
        fc = FallbackChain("qwen3.6-free", DEFAULT_MODELS)
        nxt = fc.next_after("qwen3.6-free")
        assert nxt is not None
        assert nxt != "qwen3.6-free"

    def test_next_after_invalid(self):
        from src.agents.model_router import FallbackChain, DEFAULT_MODELS
        fc = FallbackChain("qwen3.6-free", DEFAULT_MODELS)
        nxt = fc.next_after("nonexistent_model")
        assert nxt == "qwen3.6-free"

    def test_selection_has_fallback_chain(self):
        from src.agents.model_router import ModelRouter
        router = ModelRouter()
        sel = router.select("hi")
        assert sel.fallback_chain is not None
        assert len(sel.fallback_chain) > 1
        assert sel.fallback_chain[0] == sel.model_name

    def test_voice_fallback_has_personaplex(self):
        from src.agents.model_router import ModelRouter
        router = ModelRouter()
        sel = router.select("I want to speak to someone on a call")
        assert sel.voice_capable is True
        assert "nvidia-personaplex" in sel.fallback_chain


# -- 3) Cost tracking per conversation --

class TestCostTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        from src.agents.cost_tracker import CostTracker
        return CostTracker(str(tmp_path / "costs"))

    def test_record_free_model(self, tracker):
        result = tracker.record("conv_1", "qwen3.6-free", 100, 200, 350.0)
        assert result["call_cost_usd"] == 0.0

    def test_cost_calculation_paid_model(self, tracker):
        result = tracker.record("conv_2", "claude-sonnet", 1000, 500, 1200.0)
        expected = round((1000 * 3.0 + 500 * 15.0) / 1_000_000, 8)
        assert result["call_cost_usd"] == expected

    def test_accumulation(self, tracker):
        tracker.record("conv_3", "gpt-4o-mini", 100, 200, 100.0)
        tracker.record("conv_3", "gpt-4o-mini", 150, 250, 120.0)
        stats = tracker.get_conversation("conv_3")
        assert stats["call_count"] == 2
        assert stats["total_input_tokens"] == 250
        assert stats["total_output_tokens"] == 450
        assert stats["total_cost_usd"] > 0

    def test_multi_model_conversation(self, tracker):
        tracker.record("conv_4", "qwen3.6-free", 100, 100, 50.0)
        tracker.record("conv_4", "claude-sonnet", 200, 300, 800.0)
        stats = tracker.get_conversation("conv_4")
        assert stats["models_used"]["qwen3.6-free"] == 1
        assert stats["models_used"]["claude-sonnet"] == 1

    def test_pricing_table_has_personaplex(self, tracker):
        table = tracker.get_pricing_table()
        models = [r["model"] for r in table]
        assert "nvidia-personaplex" in models

    def test_persistence(self, tracker):
        tracker.record("persist_test", "gpt-4o-mini", 500, 300, 200.0)
        tracker.save_conversation("persist_test")
        from src.agents.cost_tracker import CostTracker
        t2 = CostTracker(str(Path(tracker.data_dir).parent / "costs"))
        s = t2.get_conversation("persist_test")
        assert s is not None
        assert s["call_count"] == 1


# -- 4) Model comparison dashboard --

class TestModelDashboard:
    def test_dashboard_output(self):
        from src.agents.model_router import ModelRouter
        from src.cli.commands.models import format_dashboard
        router = ModelRouter()
        out = format_dashboard(router)
        assert "Model Comparison Dashboard" in out
        assert "nvidia-personaplex" in out

    def test_summary_output(self):
        from src.agents.model_router import ModelRouter
        from src.cli.commands.models import format_summary
        out = format_summary(ModelRouter())
        assert "nvidia" in out.lower()

    def test_compare_command(self):
        from src.cli.commands.models import run_command
        out = run_command(["--compare"])
        assert "RECOMMENDATIONS" in out


# -- 5) Voice output support --

class TestVoiceOutput:
    def test_default_engine_none(self):
        from src.agents.voice_output import VoiceOutputEngine, VoiceEngine
        v = VoiceOutputEngine()
        assert v.preferred_engine == VoiceEngine.NONE

    def test_response_to_dict(self):
        from src.agents.voice_output import VoiceResponse
        vr = VoiceResponse(success=True, engine="test", text="Hello", duration_ms=500.0)
        d = vr.to_dict()
        assert d["success"] is True
        assert d["text"] == "Hello"
        assert d["duration_ms"] == 500.0

    def test_error_response_to_dict(self):
        from src.agents.voice_output import VoiceResponse
        vr = VoiceResponse(success=False, engine="test", text="", error="fail")
        d = vr.to_dict()
        assert d["success"] is False
        assert d["error"] == "fail"

    def test_none_engine_returns_disabled(self):
        from src.agents.voice_output import VoiceOutputEngine
        v = VoiceOutputEngine()
        loop = asyncio.new_event_loop()
        r = loop.run_until_complete(v.generate_voice("Hello"))
        loop.close()
        assert r.success is False

    def test_platform_callback(self):
        from src.agents.voice_output import VoiceOutputEngine, VoiceEngine
        v = VoiceOutputEngine()
        v.preferred_engine = VoiceEngine.PLATFORM_TTS
        v.register_platform_callback(lambda t: b"fake_audio")
        loop = asyncio.new_event_loop()
        r = loop.run_until_complete(v.generate_voice("Say something"))
        loop.close()
        assert r.success is True
        assert r.audio_base64 is not None

    def test_if_enabled_returns_none(self):
        from src.agents.voice_output import VoiceOutputEngine
        v = VoiceOutputEngine()
        loop = asyncio.new_event_loop()
        r = loop.run_until_complete(v.generate_voice_if_enabled("test"))
        loop.close()
        assert r is None

    def test_voice_check_cli(self):
        from src.cli.commands.voice import run_command
        out = run_command(["--check"])
        assert "Voice Engine Status" in out
        assert "PersonaPlex" in out


# -- Integration tests --

class TestIntegration:
    def test_settings_have_personaplex(self):
        from src.config.settings import Settings
        s = Settings()
        assert "gpt-oss-remote" in s.models
        assert "gemma4-remote" in s.models
        assert s.voice is not None
        assert "engine" in s.voice

    def test_settings_voice_defaults(self):
        from src.config.settings import Settings
        s = Settings()
        assert s.voice["engine"] == "none"
        assert s.voice["format"] == "wav"
        assert s.voice["persona"] == "support"

    def test_router_with_settings_models(self):
        from src.config.settings import Settings
        from src.agents.model_router import ModelRouter
        s = Settings()
        rv = ModelRouter(models=list(s.models.values()))
        sel = rv.select("help me with billing")
        assert sel.model_name is not None

    def test_router_cost_tracker_integration(self, tmp_path):
        from src.agents.model_router import ModelRouter
        from src.agents.cost_tracker import CostTracker
        tracker = CostTracker(str(tmp_path / "costs"))
        router = ModelRouter()
        sel = router.select("What is my billing?")
        tracker.record("pipeline", sel.model_name, 50, 80, 100.0)
        stats = tracker.get_conversation("pipeline")
        assert stats is not None
        assert stats["total_cost_usd"] >= 0
