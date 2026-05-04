from __future__ import annotations

import json
import ssl
from io import BytesIO
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
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Hola mundo"}
                                    ]
                                }
                            ),
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
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert "Spanish" in body["messages"][0]["content"]
    assert "JSON" in body["messages"][0]["content"]
    assert "translations" in body["messages"][0]["content"]
    assert body["messages"][1]["role"] == "user"
    assert "Hello world" in body["messages"][1]["content"]


def test_translate_segments_includes_full_transcript_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):
        calls["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Primera parte"},
                                        {"index": 2, "text": "Segunda parte"},
                                    ]
                                }
                            ),
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

    service.translate_segments(
        [
            SubtitleSegment(index=1, start=0.0, end=2.0, text="The first thought"),
            SubtitleSegment(index=2, start=2.0, end=4.0, text="continues here"),
        ]
    )

    body = calls["body"]
    system_prompt = body["messages"][0]["content"]
    user_payload = json.loads(body["messages"][1]["content"])

    assert "full transcript" in system_prompt.lower()
    assert user_payload["full_transcript"] == "The first thought\ncontinues here"
    assert user_payload["segments"] == [
        {
            "index": 1,
            "text": "The first thought",
        },
        {
            "index": 2,
            "text": "continues here",
        },
    ]


def test_translate_segments_batches_long_inputs_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode("utf-8"))
        calls.append(body)
        user_payload = json.loads(body["messages"][1]["content"])
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {
                                            "index": segment["index"],
                                            "text": f"ES {segment['index']}",
                                        }
                                        for segment in user_payload["segments"]
                                    ]
                                }
                            )
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
        source_language="English",
    )
    segments = [
        SubtitleSegment(index=index, start=float(index), end=float(index + 1), text=f"line {index}")
        for index in range(1, 46)
    ]

    result = service.translate_segments(segments)

    assert len(calls) == 2
    first_payload = json.loads(calls[0]["messages"][1]["content"])
    second_payload = json.loads(calls[1]["messages"][1]["content"])
    assert [segment["index"] for segment in first_payload["segments"]] == list(range(1, 41))
    assert [segment["index"] for segment in second_payload["segments"]] == list(range(41, 46))
    assert first_payload["source_language"] == "English"
    assert result.segments[0].text == "ES 1"
    assert result.segments[-1].text == "ES 45"
    assert "45\n00:00:45,000 --> 00:00:46,000\nES 45" in result.srt_text


def test_translate_segments_rejects_truncated_provider_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=0):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": json.dumps(
                                {"translations": [{"index": 1, "text": "Hola"}]}
                            )
                        },
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

    with pytest.raises(SubtitleTranslationError, match="truncated"):
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )


@pytest.mark.parametrize(
    ("translated_text", "error_match"),
    [
        ("00:00:01,000 Hola", "contains a timestamp"),
        ("Hola\ufffd mundo", "replacement characters"),
    ],
)
def test_translate_segments_rejects_provider_junk_inside_valid_json(
    monkeypatch: pytest.MonkeyPatch,
    translated_text: str,
    error_match: str,
) -> None:
    def fake_urlopen(request, timeout=0):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"translations": [{"index": 1, "text": translated_text}]}
                            )
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

    with pytest.raises(SubtitleTranslationError, match=error_match):
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )


def test_translate_segments_accepts_full_chat_completion_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):
        calls["url"] = request.full_url
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Bonjour le monde"}
                                    ]
                                }
                            ),
                        }
                    }
                ]
            }
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


def test_translate_segments_retries_without_response_format_for_compatible_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies: list[dict[str, object]] = []

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode("utf-8"))
        bodies.append(body)
        if "response_format" in body:
            error_body = json.dumps(
                {"error": {"message": "unsupported parameter: response_format"}}
            ).encode("utf-8")
            raise error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs={},
                fp=BytesIO(error_body),
            )
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Hola mundo"}
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://gateway.example.test/v1",
        model="custom-model",
        target_language="Spanish",
    )

    result = service.translate_segments(
        [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
    )

    assert len(bodies) == 2
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]
    assert result.txt_text == "Hola mundo"


def test_translate_segments_retries_transient_tls_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(request, timeout=0):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise error.URLError(
                ssl.SSLError(
                    "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
                )
            )
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Hola mundo"}
                                    ]
                                }
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "whisper_turbo_desktop.services.translation_service.time.sleep",
        lambda delay: None,
    )

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    result = service.translate_segments(
        [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
    )

    assert calls == 2
    assert result.txt_text == "Hola mundo"


def test_translate_segments_reports_transient_tls_failure_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(request, timeout=0):
        nonlocal calls
        calls += 1
        raise error.URLError(
            ssl.SSLError(
                "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "whisper_turbo_desktop.services.translation_service.time.sleep",
        lambda delay: None,
    )

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    with pytest.raises(SubtitleTranslationError) as exc_info:
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )

    message = str(exc_info.value)
    assert calls == 3
    assert "after 3 attempts" in message
    assert "TLS connection closed while reading the translation response" in message
    assert "Check the API endpoint" in message
    assert "urlopen error" not in message


def test_translate_segments_reports_certificate_errors_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_urlopen(request, timeout=0):
        nonlocal calls
        calls += 1
        raise error.URLError(
            ssl.SSLCertVerificationError("certificate verify failed")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    with pytest.raises(SubtitleTranslationError) as exc_info:
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )

    message = str(exc_info.value)
    assert calls == 1
    assert "certificate verification failed" in message
    assert "after 3 attempts" not in message


def test_translate_segments_rejects_non_json_model_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=0):
        return _FakeResponse(
            {"choices": [{"message": {"content": "1. Hola mundo"}}]}
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key="sk-test",
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    with pytest.raises(
        SubtitleTranslationError, match="translation response content was not valid JSON"
    ):
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )


def test_translate_segments_rejects_translation_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=0):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "translations": [
                                        {"index": 1, "text": "Hola mundo"}
                                    ]
                                }
                            )
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

    with pytest.raises(
        SubtitleTranslationError,
        match="translation response segment count mismatch: expected 2, received 1",
    ):
        service.translate_segments(
            [
                SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world"),
                SubtitleSegment(index=2, start=2.0, end=4.0, text="Goodbye"),
            ]
        )


def test_translate_segments_includes_provider_error_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "sk-secret-test"

    def fake_urlopen(request, timeout=0):
        body = json.dumps(
            {"error": {"message": f"Invalid API key: {api_key}"}}
        ).encode("utf-8")
        raise error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs={},
            fp=BytesIO(body),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    service = SubtitleTranslationService(
        api_key=api_key,
        base_url="https://api.example.com/v1",
        model="gpt-4o-mini",
        target_language="Spanish",
    )

    with pytest.raises(SubtitleTranslationError) as exc_info:
        service.translate_segments(
            [SubtitleSegment(index=1, start=0.0, end=2.0, text="Hello world")]
        )

    message = str(exc_info.value)
    assert "HTTP 401" in message
    assert "Invalid API key" in message
    assert "[redacted]" in message
    assert api_key not in message


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
