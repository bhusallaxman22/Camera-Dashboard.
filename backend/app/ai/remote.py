"""Network-backed vision providers (opt-in via AI_PROVIDER)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.ai.base import (
    CRITIQUE_SCHEMA,
    SYSTEM_PROMPT,
    AIProvider,
    AIProviderError,
    AIResult,
    PhotoContext,
    encode_preview,
    result_from_json,
)
from app.config import get_settings


def _user_prompt(photo: PhotoContext) -> str:
    return "Critique this photograph.\n\n" + "\n".join(photo.summary_lines())


class OpenAIProvider(AIProvider):
    name = "openai"

    def is_configured(self) -> bool:
        return bool(get_settings().openai_api_key)

    def analyze_photo(self, photo: PhotoContext, preview: Path) -> AIResult:
        s = get_settings()
        if not s.openai_api_key:
            raise AIProviderError("OPENAI_API_KEY is not set")
        image_b64 = encode_preview(preview)
        body = {
            "model": s.openai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _user_prompt(photo)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "high"},
                        },
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "photo_critique", "strict": True, "schema": CRITIQUE_SCHEMA},
            },
        }
        try:
            resp = httpx.post(
                f"{s.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {s.openai_api_key}"},
                json=body,
                timeout=s.ai_timeout_seconds,
            )
            resp.raise_for_status()
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(f"OpenAI HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc
        result = result_from_json(data, payload.get("model", s.openai_model))
        result.model_version = payload.get("system_fingerprint")
        return result


class OllamaProvider(AIProvider):
    """Local vision LLM via Ollama (e.g. qwen2.5vl, llava, gemma3)."""

    name = "ollama"

    def is_configured(self) -> bool:
        return bool(get_settings().ollama_url)

    def analyze_photo(self, photo: PhotoContext, preview: Path) -> AIResult:
        s = get_settings()
        if not s.ollama_url:
            raise AIProviderError("OLLAMA_URL is not set")
        body = {
            "model": s.ollama_model,
            "stream": False,
            "format": CRITIQUE_SCHEMA,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(photo), "images": [encode_preview(preview)]},
            ],
        }
        try:
            resp = httpx.post(f"{s.ollama_url.rstrip('/')}/api/chat", json=body, timeout=s.ai_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json()
            data = json.loads(payload["message"]["content"])
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"Ollama request failed: {exc}") from exc
        return result_from_json(data, payload.get("model", s.ollama_model))
