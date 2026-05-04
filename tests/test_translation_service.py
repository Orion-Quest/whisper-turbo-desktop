from __future__ import annotations

import json
from urllib import error

import pytest

from whisper_turbo_desktop.services.translation_service import (
    SubtitleSegment,
    SubtitleTranslationError,
    SubtitleTranslationService,
)


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_translate_segments_posts_chat_completion_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):
        calls["url"] = request.full_url
        calls["method"] = request.get_method()
        calls["auth"] = request.headers.get("Authorization")
        calls["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "1\n00:00:00,000 --> 00:00:02,000\nHola mundo",
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    result = service.translate_segments(
        [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
    )

    assert result.srt_text == "1\n00:00:00,000 --> 00:00:02,000\nHola mundo"
    assert result.segments[0].text == "Hola mundo"
    assert calls["url"] == "https://api.example.com/v1/chat/completions"
    assert calls["method"] == "POST"
    assert calls["auth"] == "Bearer sk-test"
    body = calls["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0
    assert body["messages"][0]["role"] == "system"
    assert "Spanish" in body["messages"][0]["content"]
    assert body["messages"][1]["role"] == "user"
    assert "Hello world" in body["messages"][1]["content"]


def test_translate_segments_accepts_full_chat_completion_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):
        calls["url"] = request.full_url
        return _FakeResponse(
            {"choices": [{"message": {"content": "Bonjour le monde"}}]}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://gateway.example.test/openai/chat/completions",
        model="custom-model",
        target_language="French",
    )

    result = service.translate_segments(
        [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
    )

    assert calls["url"] == "https://gateway.example.test/openai/chat/completions"
    assert result.txt_text == "Bonjour le monde"


def test_translate_segments_raises_explicit_error_for_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=0):
        return _FakeResponse({"choices": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    with pytest.raises(SubtitleTranslationError, match="translation response did not contain text"):
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )
