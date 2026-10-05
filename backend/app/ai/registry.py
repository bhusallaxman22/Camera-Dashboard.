from __future__ import annotations

from app.ai.base import AIProvider
from app.ai.local import LocalBasicProvider
from app.ai.remote import OllamaProvider, OpenAIProvider
from app.config import get_settings

PROVIDERS: dict[str, type[AIProvider]] = {
    "local": LocalBasicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str | None = None) -> AIProvider | None:
    """Return the requested (or configured) provider; None when AI is disabled."""
    key = name or get_settings().ai_provider
    if key == "none":
        return None
    cls = PROVIDERS.get(key)
    if cls is None:
        raise ValueError(f"unknown AI provider: {key}")
    return cls()


def describe_providers() -> list[dict]:
    active = get_settings().ai_provider
    return [{**cls().describe(), "active": key == active} for key, cls in PROVIDERS.items()]
