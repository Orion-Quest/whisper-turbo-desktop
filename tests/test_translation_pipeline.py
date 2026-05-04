from __future__ import annotations

from pathlib import Path

import pytest

import whisper_turbo_desktop.services.whisper_runner as whisper_runner
from whisper_turbo_desktop.models.transcription import TranscriptionRequest
from whisper_turbo_desktop.services.whisper_runner import TranscriptionWorker


def test_translation_pipeline_writes_translated_subtitles(
    tmp_path: Path, monkeypatch
) -> None:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake audio")
    output_dir = tmp_path / "out"

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return {
                "segments": [
                    {"id": 0, "start": 0.0, "end": 1.0, "text": "Hello"},
                ],
                "text": "Hello",
            }

    class FakeWriter:
        def __call__(self, result, _input_path: str) -> None:
            (output_dir / "input.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                encoding="utf-8",
            )
            (output_dir / "input.backup.srt").write_text(
                "unrelated same-prefix subtitle\n",
                encoding="utf-8",
            )
            (output_dir / "input.translated.json").write_text(
                "{}",
                encoding="utf-8",
            )

    class FakeTranslator:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def translate_segments(self, segments):
            assert [segment.text for segment in segments] == ["Hello"]
            assert [segment.index for segment in segments] == [1]
            translated_srt = "1\n00:00:00,000 --> 00:00:01,000\nHola\n"
            translated_vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nHola\n"
            translated_txt = "Hola\n"
            return type(
                "TranslatedSubtitleResult",
                (),
                {
                    "srt_text": translated_srt,
                    "vtt_text": translated_vtt,
                    "txt_text": translated_txt,
                },
            )()

    monkeypatch.setattr(
        whisper_runner, "get_writer", lambda _format, _dir: FakeWriter()
    )
    monkeypatch.setattr(
        whisper_runner.whisper, "load_model", lambda *args, **kwargs: FakeModel()
    )
    monkeypatch.setattr(
        whisper_runner,
        "SubtitleTranslationService",
        lambda **kwargs: FakeTranslator(**kwargs),
    )
    monkeypatch.setattr(whisper_runner, "resolve_model_source", lambda model: model)
    monkeypatch.setattr(whisper_runner, "is_model_cached", lambda _model: True)
    monkeypatch.setattr(whisper_runner, "local_whisper_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(whisper_runner.torch.cuda, "is_available", lambda: False)

    request = TranscriptionRequest(
        input_path=input_path,
        output_dir=output_dir,
        model="turbo",
        task="transcribe",
        language=None,
        device="auto",
        output_format="srt",
        translation_enabled=True,
        translation_api_key="sk-test",
        translation_base_url="https://api.example.com/v1",
        translation_model="gpt-4o-mini",
        translation_target_language="Spanish",
    )

    result_holder: list[object] = []
    failure_holder: list[object] = []

    worker = TranscriptionWorker(request)
    worker.finished_success.connect(result_holder.append)
    worker.failed.connect(failure_holder.append)
    worker.run()

    assert failure_holder == []
    assert len(result_holder) == 1
    result = result_holder[0]
    output_files = {path.name for path in result.output_files}

    assert output_files == {
        "input.srt",
        "input.translated.srt",
        "input.translated.txt",
        "input.translated.vtt",
    }
    assert (output_dir / "input.translated.srt").exists()
    assert (output_dir / "input.translated.vtt").exists()
    assert (output_dir / "input.translated.txt").exists()
    assert (
        (output_dir / "input.translated.srt").read_text(encoding="utf-8")
        == "1\n00:00:00,000 --> 00:00:01,000\nHola\n"
    )


def test_translation_pipeline_uses_source_transcript_for_sidecar_translation_when_whisper_translates_to_english(
    tmp_path: Path, monkeypatch
) -> None:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake audio")
    output_dir = tmp_path / "out"
    transcribe_tasks: list[str] = []

    class FakeModel:
        def transcribe(self, *_args, **kwargs):
            transcribe_tasks.append(kwargs["task"])
            if kwargs["task"] == "translate":
                return {
                    "segments": [
                        {
                            "id": 0,
                            "start": 0.0,
                            "end": 1.0,
                            "text": "This is Whisper English.",
                        },
                    ],
                    "text": "This is Whisper English.",
                }
            return {
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": 1.0,
                        "text": "Esto es el texto original.",
                    },
                ],
                "text": "Esto es el texto original.",
            }

    class FakeWriter:
        def __call__(self, result, _input_path: str) -> None:
            assert result["text"] == "This is Whisper English."
            (output_dir / "input.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nThis is Whisper English.\n",
                encoding="utf-8",
            )

    class FakeTranslator:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def translate_segments(self, segments):
            assert [segment.text for segment in segments] == [
                "Esto es el texto original."
            ]
            translated_srt = (
                "1\n00:00:00,000 --> 00:00:01,000\nこれは元のテキストです。\n"
            )
            translated_vtt = (
                "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\n"
                "これは元のテキストです。\n"
            )
            translated_txt = "これは元のテキストです。\n"
            return type(
                "TranslatedSubtitleResult",
                (),
                {
                    "srt_text": translated_srt,
                    "vtt_text": translated_vtt,
                    "txt_text": translated_txt,
                },
            )()

    monkeypatch.setattr(
        whisper_runner, "get_writer", lambda _format, _dir: FakeWriter()
    )
    monkeypatch.setattr(
        whisper_runner.whisper, "load_model", lambda *args, **kwargs: FakeModel()
    )
    monkeypatch.setattr(
        whisper_runner,
        "SubtitleTranslationService",
        lambda **kwargs: FakeTranslator(**kwargs),
    )
    monkeypatch.setattr(whisper_runner, "resolve_model_source", lambda model: model)
    monkeypatch.setattr(whisper_runner, "is_model_cached", lambda _model: True)
    monkeypatch.setattr(whisper_runner, "local_whisper_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(whisper_runner.torch.cuda, "is_available", lambda: False)

    request = TranscriptionRequest(
        input_path=input_path,
        output_dir=output_dir,
        model="turbo",
        task="translate",
        language="Spanish",
        device="auto",
        output_format="srt",
        translation_enabled=True,
        translation_api_key="sk-test",
        translation_base_url="https://api.example.com/v1",
        translation_model="gpt-4o-mini",
        translation_target_language="Japanese",
    )

    result_holder: list[object] = []
    failure_holder: list[object] = []

    worker = TranscriptionWorker(request)
    worker.finished_success.connect(result_holder.append)
    worker.failed.connect(failure_holder.append)
    worker.run()

    assert failure_holder == []
    assert len(result_holder) == 1
    assert transcribe_tasks == ["translate", "transcribe"]
    assert (
        (output_dir / "input.translated.srt").read_text(encoding="utf-8")
        == "1\n00:00:00,000 --> 00:00:01,000\nこれは元のテキストです。\n"
    )


def test_translation_request_requires_api_key(tmp_path: Path) -> None:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake audio")

    request = TranscriptionRequest(
        input_path=input_path,
        output_dir=tmp_path / "out",
        translation_enabled=True,
        translation_target_language="Spanish",
        translation_api_key="",
    )

    with pytest.raises(ValueError, match="Translation API key must not be empty"):
        request.validate()
