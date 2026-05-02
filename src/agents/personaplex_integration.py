"""
PersonaPlex Integration — NVIDIA's Full-Duplex Voice Dialogue Model
===================================================================
For SupportOID: Voice-enabled customer support with natural interruptions.

From NVIDIA personaplex (7B, speech-to-speech):
  • Full-duplex conversation (listen + speak simultaneously)
  • Customizable personas via text prompts
  • Natural backchanneling ("uh-huh", "oh", etc.)
  • Interruption handling
  • Accent and voice control

Requirements for local deployment:
  • NVIDIA GPU (any with 8GB+ VRAM)
  • 8GB+ RAM
  • Docker or Python 3.12+

For cloud (NIM API) — no GPU required on our side.
"""

import json, time
try:
    import requests
except ImportError:
    requests = None
from typing import Optional, Dict


class PersonaPlexIntegration:
    """
    NVIDIA PersonaPlex integration for SupportOID.
    Two modes: NIM API (cloud) or Local (self-hosted GPU).
    """

    AGENT_PERSONAS = {
        "support": "You are a helpful and empathetic customer support agent for Lehro Solutions. "
                   "Be patient, clear, and solution-oriented. Use natural backchanneling "
                   "like 'I understand', 'I see', 'Let me help with that'. "
                   "Handle technical issues, billing questions, feature requests, and account management.",
        "technical": "You are a senior technical support engineer for Lehro Solutions. "
                     "You are knowledgeable, precise, and efficient. Use clear technical language "
                     "but keep it accessible. Handle API issues, infrastructure, and deployment questions.",
        "friendly": "You are a friendly, conversational AI assistant. You enjoy having a good "
                    "conversation while being genuinely helpful. Use natural interruptions "
                    "and backchanneling like 'oh okay', 'yeah', 'I see what you mean'."
    }

    def __init__(self, mode: str = "nim", nim_api_key: str = None, local_endpoint: str = "http://localhost:8080"):
        self.mode = mode
        self.nim_api_key = nim_api_key
        self.local_endpoint = local_endpoint

    def is_available(self) -> bool:
        if self.mode == "nim":
            return bool(self.nim_api_key)
        if requests is None:
            return False
        try:
            r = requests.get(f"{self.local_endpoint}/health", timeout=2)
            return r.status_code == 200
        except:
            return False

    async def generate_speech(self, text: str, persona: str = "support") -> Optional[bytes]:
        """
        Generate personalized speech response from PersonaPlex model.
        Returns audio bytes or None.
        """
        if requests is None:
            return None
        persona_text = self.AGENT_PERSONAS.get(persona, self.AGENT_PERSONAS["support"])
        
        if self.mode == "nim":
            resp = requests.post(
                "https://integrate.api.nvidia.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {self.nim_api_key}"},
                json={"model": "nvidia/personaplex-7b-v1", "input": text, 
                      "persona": persona_text})
            resp.raise_for_status()
            return resp.content

    async def stream_voice_conversation(self, audio_stream, persona: str = "support"):
        """
        Full-duplex voice conversation - listen and speak simultaneously.
        For real-time voice-to-voice dialogue with natural interruptions.
        """
        if self.mode == "local":
            # WebSocket to local PersonaPlex server
            import websockets
            async with websockets.connect(f"ws://{self.local_endpoint}/ws/conversation") as ws:
                await ws.send(json.dumps({"persona": self.AGENT_PERSONAS.get(persona)}))
                async for audio_chunk in audio_stream:
                    await ws.send(audio_chunk)
                    response = await ws.recv()
                    yield json.loads(response)
