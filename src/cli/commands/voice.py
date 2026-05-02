"""
Voice Command — CLI
====================
Usage:
  python -m src.cli voice "Hello, this is a test"     # Generate voice output
  python -m src.cli voice --check                      # Check voice engine status
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


def run_command(args=None) -> str:
    import argparse
    parser = argparse.ArgumentParser(description="Voice output engine")
    parser.add_argument("text", nargs="?", default=None, help="Text to convert to speech")
    parser.add_argument("--check", action="store_true", help="Check voice engine availability")
    parsed = parser.parse_args(args)

    if parsed.check:
        lines = ["Voice Engine Status", "=" * 40]
        
        # Check PersonaPlex
        from src.agents.personaplex_integration import PersonaPlexIntegration
        pp = PersonaPlexIntegration(mode="nim")
        pp_available = pp.is_available()
        lines.append(f"  PersonaPlex (NIM):  {'Available' if pp_available else 'Not configured (no API key)'}")
        
        # Check local personaplex
        pp_local = PersonaPlexIntegration(mode="local")
        pp_local_available = pp_local.is_available()
        lines.append(f"  PersonaPlex (Local): {'Available' if pp_local_available else 'Not running locally'}")
        
        # Check platform TTS
        from src.agents.voice_output import VoiceOutputEngine, VoiceEngine
        voice = VoiceOutputEngine()
        lines.append(f"  Platform TTS:       {'Ready (callback needed)' if voice._platform_tts_callback else 'Not registered'}")
        lines.append(f"  Preferred Engine:   {voice.preferred_engine.value}")
        lines.append(f"  Preferred Format:   {voice.preferred_format}")
        lines.insert(1, "=" * 40)
        return "\n".join(lines)

    if parsed.text:
        return f"Voice output requested for: \"{parsed.text[:100]}\"\nNote: Voice generation requires TTS callback registration. PersonaPlex needs NIM API key."

    return "Usage: python -m src.cli voice <text>  OR  python -m src.cli voice --check"
