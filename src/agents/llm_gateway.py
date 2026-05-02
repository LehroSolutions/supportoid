"""LLM gateway for OpenAI-compatible Responses and Chat Completions backends."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class ModelProfile:
    name: str
    family: str
    provider: str
    base_url: str
    api_key: str
    model_id: str
    transport: str
    enabled: bool = True
    priority: int = 99
    reasoning_effort: str = "medium"
    max_tokens: int = 4096
    supports_structured_output: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.base_url.strip())


@dataclass
class GatewayAttempt:
    profile_name: str
    family: str
    transport: str
    ok: bool
    latency_ms: float
    error: str = ""
    response_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    raw_text: str = ""
    payload: Optional[Dict[str, Any]] = None

    def to_trace(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.payload is None:
            data["payload"] = None
        return data


@dataclass
class GatewayStatus:
    active_chain: list[str] = field(default_factory=list)
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class LLMGateway:
    """Routes structured prompts to configured OpenAI-compatible providers."""

    def __init__(self, settings):
        self.timeout_ms = int(getattr(settings, "llm_timeout_ms", 15000) or 15000)
        self.model_chain = list(getattr(settings, "model_chain", []) or [])
        self.profiles = self._load_profiles(getattr(settings, "models", {}) or {})

    @staticmethod
    def _load_profiles(raw_profiles: Dict[str, Dict[str, Any]]) -> Dict[str, ModelProfile]:
        profiles: Dict[str, ModelProfile] = {}
        for key, raw in raw_profiles.items():
            if not isinstance(raw, dict):
                continue
            if not raw.get("transport"):
                continue
            profiles[str(key)] = ModelProfile(
                name=str(raw.get("name") or key),
                family=str(raw.get("family") or "unknown"),
                provider=str(raw.get("provider") or "openai-compatible"),
                base_url=str(raw.get("base_url") or "").strip(),
                api_key=str(raw.get("api_key") or "").strip(),
                model_id=str(raw.get("model_id") or key),
                transport=str(raw.get("transport") or "chat_completions"),
                enabled=bool(raw.get("enabled", True)),
                priority=int(raw.get("priority", 99) or 99),
                reasoning_effort=str(raw.get("reasoning_effort") or "medium"),
                max_tokens=int(raw.get("max_tokens", 4096) or 4096),
                supports_structured_output=bool(
                    raw.get("supports_structured_output", True)
                ),
            )
        return profiles

    def ordered_profiles(self) -> list[ModelProfile]:
        ordered: list[ModelProfile] = []
        seen: set[str] = set()
        for name in self.model_chain:
            profile = self.profiles.get(name)
            if profile is None:
                continue
            ordered.append(profile)
            seen.add(name)

        for name, profile in sorted(
            self.profiles.items(), key=lambda item: (item[1].priority, item[0])
        ):
            if name in seen:
                continue
            ordered.append(profile)
        return ordered

    def runtime_status(self) -> GatewayStatus:
        profiles: Dict[str, Dict[str, Any]] = {}
        for name, profile in self.profiles.items():
            profiles[name] = {
                "family": profile.family,
                "transport": profile.transport,
                "configured": profile.configured,
                "enabled": profile.enabled,
                "provider": profile.provider,
                "model_id": profile.model_id,
            }
        return GatewayStatus(active_chain=self.model_chain or [], profiles=profiles)

    def invoke_profile(
        self,
        profile: ModelProfile,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
        previous_response_id: str = "",
    ) -> GatewayAttempt:
        start = time.monotonic()
        if requests is None:
            return GatewayAttempt(
                profile_name=profile.name,
                family=profile.family,
                transport=profile.transport,
                ok=False,
                latency_ms=0.0,
                error="requests_unavailable",
            )

        if not profile.configured:
            return GatewayAttempt(
                profile_name=profile.name,
                family=profile.family,
                transport=profile.transport,
                ok=False,
                latency_ms=0.0,
                error="profile_not_configured",
            )

        try:
            if profile.transport == "responses":
                payload = self._call_responses_api(
                    profile,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                    previous_response_id=previous_response_id,
                )
            else:
                payload = self._call_chat_completions_api(
                    profile,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                )
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return GatewayAttempt(
                profile_name=profile.name,
                family=profile.family,
                transport=profile.transport,
                ok=True,
                latency_ms=latency_ms,
                response_id=str(payload.get("response_id") or ""),
                input_tokens=int(payload.get("input_tokens", 0) or 0),
                output_tokens=int(payload.get("output_tokens", 0) or 0),
                raw_text=str(payload.get("raw_text") or ""),
                payload=payload.get("payload"),
            )
        except Exception as exc:
            return GatewayAttempt(
                profile_name=profile.name,
                family=profile.family,
                transport=profile.transport,
                ok=False,
                latency_ms=round((time.monotonic() - start) * 1000, 1),
                error=str(exc),
            )

    def _call_responses_api(
        self,
        profile: ModelProfile,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
        previous_response_id: str = "",
    ) -> Dict[str, Any]:
        url = self._endpoint(profile.base_url, "responses")
        request_payload: Dict[str, Any] = {
            "model": profile.model_id,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": profile.max_tokens,
            "reasoning": {"effort": profile.reasoning_effort},
        }
        if previous_response_id:
            request_payload["previous_response_id"] = previous_response_id
        if profile.supports_structured_output:
            request_payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "support_response",
                    "schema": schema,
                }
            }
        response = requests.post(
            url,
            json=request_payload,
            headers=self._headers(profile.api_key),
            timeout=self.timeout_ms / 1000.0,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{profile.name} returned {response.status_code}")
        data = response.json()
        raw_text = self._responses_text(data)
        payload = self._extract_payload(data.get("output_parsed"), raw_text)
        usage = data.get("usage") or {}
        return {
            "payload": payload,
            "raw_text": raw_text,
            "response_id": data.get("id") or "",
            "input_tokens": usage.get("input_tokens", 0)
            or usage.get("prompt_tokens", 0)
            or 0,
            "output_tokens": usage.get("output_tokens", 0)
            or usage.get("completion_tokens", 0)
            or 0,
        }

    def _call_chat_completions_api(
        self,
        profile: ModelProfile,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        url = self._endpoint(profile.base_url, "chat/completions")
        request_payload: Dict[str, Any] = {
            "model": profile.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": profile.max_tokens,
            "temperature": 0.2,
        }
        if profile.reasoning_effort:
            request_payload["reasoning_effort"] = profile.reasoning_effort
        if profile.supports_structured_output:
            request_payload["response_format"] = {"type": "json_object"}
        response = requests.post(
            url,
            json=request_payload,
            headers=self._headers(profile.api_key),
            timeout=self.timeout_ms / 1000.0,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"{profile.name} returned {response.status_code}")
        data = response.json()
        choice = ((data.get("choices") or [{}])[0]).get("message") or {}
        raw_text = str(choice.get("content") or "")
        payload = self._extract_payload(choice.get("parsed"), raw_text)
        usage = data.get("usage") or {}
        return {
            "payload": payload,
            "raw_text": raw_text,
            "response_id": data.get("id") or "",
            "input_tokens": usage.get("prompt_tokens", 0)
            or usage.get("input_tokens", 0)
            or 0,
            "output_tokens": usage.get("completion_tokens", 0)
            or usage.get("output_tokens", 0)
            or 0,
        }

    @staticmethod
    def _headers(api_key: str) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def _endpoint(base_url: str, path: str) -> str:
        base = (base_url or "").rstrip("/")
        if base.endswith(path):
            return base
        if base.endswith("/v1"):
            return f"{base}/{path}"
        if "/v1/" in base:
            return f"{base}/{path}"
        return f"{base}/v1/{path}"

    @staticmethod
    def _responses_text(data: Dict[str, Any]) -> str:
        direct = data.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct

        chunks: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if isinstance(content, dict):
                    text = content.get("text") or content.get("value") or ""
                    if text:
                        chunks.append(str(text))
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    @staticmethod
    def _extract_payload(parsed: Any, raw_text: str) -> Dict[str, Any]:
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str) and parsed.strip():
            try:
                loaded = json.loads(parsed)
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                pass

        match = JSON_BLOCK_RE.search(raw_text or "")
        if match:
            raw_text = match.group(1)

        raw_text = (raw_text or "").strip()
        if not raw_text:
            raise ValueError("empty_response")

        loaded = json.loads(raw_text)
        if not isinstance(loaded, dict):
            raise ValueError("structured_payload_must_be_object")
        return loaded


def iter_structured_attempts(
    gateway: LLMGateway,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    previous_response_id: str = "",
    profiles: Optional[Iterable[ModelProfile]] = None,
) -> list[GatewayAttempt]:
    attempts: list[GatewayAttempt] = []
    for profile in profiles or gateway.ordered_profiles():
        attempts.append(
            gateway.invoke_profile(
                profile,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                previous_response_id=previous_response_id,
            )
        )
    return attempts
