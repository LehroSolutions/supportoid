"""
Voice Output Engine — SupportOID
================================
Provides text-to-speech voice output for support responses.
Supports:
  • NVIDIA PersonaPlex (natural, persona-aware speech)
  • Platform TTS fallback (OpenClaw tts tool)
  • Audio format selection (wav / mp3 / ogg)
  • Voice response metadata for API consumers
"""
import base64, logging, time
from enum import Enum
from typing import Optional
from dataclasses import dataclass


logger = logging.getLogger("supportoid.voice")


class VoiceEngine(str, Enum):
    PERSONAPLEX = "personaplex"
    PLATFORM_TTS = "platform_tts"
    NONE = "none"


class AudioFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"


@dataclass
class VoiceResponse:
    """Container for voice output metadata."""
    success: bool
    engine: str
    audio_base64: Optional[str] = None   # base64-encoded audio
    audio_format: Optional[str] = None
    duration_ms: Optional[float] = None
    text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "success": self.success,
            "engine": self.engine,
            "text": self.text,
        }
        if self.audio_base64:
            d["audio_base64"] = self.audio_base64
        if self.audio_format:
            d["audio_format"] = self.audio_format
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.error:
            d["error"] = self.error
        return d


class VoiceOutputEngine:
    """
    Voice output for SupportOID responses.
    Tries PersonaPlex first, falls back to platform TTS.
    """

    def __init__(self, personaplex=None, settings=None):
        """
        Args:
            personaplex: Optional PersonaPlexIntegration instance
            settings:  Optional settings object with voice config
        """
        self.personaplex = personaplex
        self._platform_tts_callback = None  # set externally (e.g., from CLI or API)

        # Voice preferences (can be overridden via settings)
        self.preferred_engine = VoiceEngine.NONE
        self.preferred_format = AudioFormat.WAV
        self.voice_persona = "support"

        if settings:
            voice_cfg = getattr(settings, "voice", {}) or {}
            if voice_cfg.get("engine"):
                try:
                    self.preferred_engine = VoiceEngine(voice_cfg["engine"])
                except ValueError:
                    pass
            if voice_cfg.get("format"):
                try:
                    self.preferred_format = AudioFormat(voice_cfg["format"])
                except ValueError:
                    pass
            if voice_cfg.get("persona"):
                self.voice_persona = voice_cfg["persona"]

    def register_platform_callback(self, callback):
        """Register a platform TTS callback (e.g., OpenClaw tts integration)."""
        self._platform_tts_callback = callback

    async def generate_voice(self, text: str) -> VoiceResponse:
        """Generate voice output from text response."""
        if self.preferred_engine == VoiceEngine.NONE:
            return VoiceResponse(success=False, engine="none", text=text)

        if self.preferred_engine == VoiceEngine.PERSONAPLEX:
            try:
                result = await self._generate_personaplex(text)
                if result and result.success:
                    return result
            except Exception as e:
                logger.warning(f"PersonaPlex voice failed, falling back: {e}")

        # Fallback: platform TTS
        return self._generate_platform_tts(text)

    async def _generate_personaplex(self, text: str) -> Optional[VoiceResponse]:
        """Generate speech via NVIDIA PersonaPlex."""
        if not self.personaplex or not self.personaplex.is_available():
            return None

        start = time.monotonic()
        audio_bytes = await self.personaplex.generate_speech(
            text, persona=self.voice_persona)
        latency_ms = (time.monotonic() - start) * 1000

        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode()
            # Estimate duration: roughly 25 bytes per ms for 16-bit 24kHz PCM wav
            estimated_duration_ms = len(audio_bytes) / 48.0  # rough estimate
            return VoiceResponse(
                success=True,
                engine=VoiceEngine.PERSONAPLEX,
                audio_base64=audio_b64,
                audio_format="raw",  # personaplex returns raw audio
                duration_ms=round(estimated_duration_ms, 1),
                text=text,
            )
        return None

    def _generate_platform_tts(self, text: str) -> VoiceResponse:
        """Generate speech via platform TTS callback."""
        if not self._platform_tts_callback:
            return VoiceResponse(
                success=False, engine="platform_tts", text=text,
                error="No platform TTS callback registered")

        try:
            start = time.monotonic()
            audio_data = self._platform_tts_callback(text)
            latency_ms = (time.monotonic() - start) * 1000

            if isinstance(audio_data, bytes):
                audio_b64 = base64.b64encode(audio_data).decode()
            else:
                audio_b64 = str(audio_data)

            return VoiceResponse(
                success=True,
                engine=VoiceEngine.PLATFORM_TTS,
                audio_base64=audio_b64,
                audio_format=self.preferred_format,
                duration_ms=round(latency_ms, 1),
                text=text,
            )
        except Exception as e:
            logger.error(f"Platform TTS failed: {e}")
            return VoiceResponse(
                success=False, engine="platform_tts", text=text,
                error=str(e))

    async def generate_voice_if_enabled(self, text: str) -> Optional[VoiceResponse]:
        """Generate voice only if engine is configured."""
        if self.preferred_engine == VoiceEngine.NONE:
            return None
        return await self.generate_voice(text)
