from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from PIL import Image

from tests.conftest import _clear_caches, age_files, requires_exiftool, write_capture

CRITIQUE = {
    "scene": "Portrait",
    "subject": "young woman",
    "description": "A candid portrait on a sofa.",
    "composition": ["subject slightly off-centre"],
    "technical": ["1/60 is borderline handheld"],
    "issues": ["busy kitchen background"],
    "suggestions": ["raise shutter speed to 1/125"],
    "tags": ["Portrait", "indoor"],
    "aesthetic_score": 6.5,
    "confidence": 0.9,
}


class FakeOllama:
    """Stands in for httpx.post against /api/chat and records the request body."""

    def __init__(self, message: dict, status: int = 200, done_reason: str = "stop") -> None:
        self.message, self.status, self.done_reason = message, status, done_reason
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, json: dict, timeout: float) -> httpx.Response:
        self.calls.append((url, json))
        payload = {"model": json["model"], "message": self.message, "done_reason": self.done_reason}
        return httpx.Response(self.status, json=payload, request=httpx.Request("POST", url))


@pytest.fixture
def ollama_env(env, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.test:11434/")
    _clear_caches()
    return env


@pytest.fixture
def preview(tmp_path: Path) -> Path:
    p = tmp_path / "preview.jpg"
    Image.new("RGB", (1600, 1000), (90, 120, 160)).save(p, "JPEG")
    return p


def _analyze(monkeypatch, fake: FakeOllama, preview: Path):
    from app.ai import remote
    from app.ai.base import PhotoContext

    monkeypatch.setattr(remote.httpx, "post", fake)
    ctx = PhotoContext(photo_id="p1", filename="DSC_0001.JPG", camera="NIKON Z6_3", aperture=2.8, iso=1100)
    return remote.OllamaProvider().analyze_photo(ctx, preview)


def test_extract_json_object_tolerates_fences_and_prose():
    from app.ai.base import extract_json_object

    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Here you go: {"a": {"b": [1, 2]}} hope it helps {"x": 0}') == {"a": {"b": [1, 2]}}
    for bad in ("no json here", "[1, 2]", '{"a": '):
        with pytest.raises(ValueError):
            extract_json_object(bad)


def test_schema_instructions_list_every_key():
    from app.ai.base import CRITIQUE_SCHEMA, schema_instructions

    text = schema_instructions()
    for key in CRITIQUE_SCHEMA["required"]:
        assert f'"{key}"' in text


def test_ollama_request_and_fenced_reply(ollama_env, monkeypatch, preview):
    fake = FakeOllama({"role": "assistant", "content": "```json\n" + json.dumps(CRITIQUE) + "\n```"})
    result = _analyze(monkeypatch, fake, preview)

    url, body = fake.calls[0]
    assert url == "http://ollama.test:11434/api/chat"
    assert body["model"] == "gemma4:26b"
    assert body["keep_alive"] == "30m"
    assert body["stream"] is False and "format" in body
    assert body["think"] is False
    assert '"aesthetic_score"' in body["messages"][0]["content"]
    assert "Exposure: f/2.8, ISO 1100" in body["messages"][1]["content"]
    assert len(body["messages"][1]["images"]) == 1

    assert result.scene == "portrait"
    assert result.tags == ["portrait", "indoor"]
    assert result.aesthetic_score == 6.5
    assert result.model_name == "gemma4:26b"


def test_ollama_think_and_keep_alive_are_configurable(ollama_env, monkeypatch, preview):
    monkeypatch.setenv("OLLAMA_THINK", "true")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "5m")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5vl:7b")
    _clear_caches()
    fake = FakeOllama({"content": json.dumps(CRITIQUE)})
    _analyze(monkeypatch, fake, preview)
    body = fake.calls[0][1]
    assert body["think"] is True
    assert body["keep_alive"] == "5m"
    assert body["model"] == "qwen2.5vl:7b"

    monkeypatch.setenv("OLLAMA_THINK", "")
    _clear_caches()
    _analyze(monkeypatch, fake, preview)
    assert "think" not in fake.calls[1][1]


def test_ollama_json_in_thinking_field_is_used(ollama_env, monkeypatch, preview):
    fake = FakeOllama({"content": "", "thinking": "Let me look... " + json.dumps(CRITIQUE)})
    assert _analyze(monkeypatch, fake, preview).subject == "young woman"


@pytest.mark.parametrize(
    ("fake", "match"),
    [
        (FakeOllama({"content": "I cannot help with that."}), "no JSON critique"),
        (FakeOllama({"content": '{"scene": "por'}, done_reason="length"), "cut off"),
        (FakeOllama({"error": "model not found"}, status=404), "Ollama HTTP 404"),
    ],
)
def test_ollama_failures_raise_provider_error(ollama_env, monkeypatch, preview, fake, match):
    from app.ai.base import AIProviderError

    with pytest.raises(AIProviderError, match=match):
        _analyze(monkeypatch, fake, preview)


def test_ollama_unreachable_raises_provider_error(ollama_env, monkeypatch, preview):
    from app.ai import remote
    from app.ai.base import AIProviderError, PhotoContext

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(remote.httpx, "post", boom)
    with pytest.raises(AIProviderError, match="request failed"):
        remote.OllamaProvider().analyze_photo(PhotoContext(photo_id="p", filename="x.jpg"), preview)


def test_ollama_provider_reports_model(ollama_env):
    from app.ai.registry import describe_providers

    ollama = next(p for p in describe_providers() if p["name"] == "ollama")
    assert ollama == {"name": "ollama", "configured": True, "model": "gemma4:26b", "active": True}


@requires_exiftool
def test_pipeline_stores_ollama_critique(ollama_env, db, monkeypatch):
    from sqlalchemy import select

    from app.ai import remote
    from app.models import AICritique, Photo
    from app.services.pipeline import process_file_inline

    fake = FakeOllama({"content": json.dumps(CRITIQUE)})
    monkeypatch.setattr(remote.httpx, "post", fake)
    files = write_capture(ollama_env["photos"], "DSC_0100", datetime(2026, 5, 1, 10, 0, 0), raw=False)
    age_files(ollama_env["photos"])
    process_file_inline(files["jpeg"])

    critique = db.scalars(select(AICritique)).one()
    assert (critique.provider, critique.status, critique.model_name) == ("ollama", "succeeded", "gemma4:26b")
    assert critique.suggestions == ["raise shutter speed to 1/125"]
    assert db.scalars(select(Photo)).one().scene == "portrait"
    assert len(fake.calls) == 1
