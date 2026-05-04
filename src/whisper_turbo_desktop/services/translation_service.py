from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

MAX_TRANSLATION_SEGMENTS_PER_REQUEST = 40
MAX_TRANSLATION_SOURCE_CHARS_PER_REQUEST = 7000
TRANSLATION_CONTEXT_SEGMENTS = 3
MAX_TRANSLATION_CONTEXT_CHARS = 5000
TIMESTAMP_PATTERN = re.compile(r"\b\d{2}:\d{2}:\d{2}[,.]\d{3}\b")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass(slots=True)
class SubtitleSegment:
    index: int
    start: float
    end: float
    text: str


@dataclass(slots=True)
class TranslatedSubtitleResult:
    segments: list[SubtitleSegment]
    srt_text: str
    vtt_text: str
    txt_text: str


class SubtitleTranslationError(RuntimeError):
    pass


class SubtitleTranslationService:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        target_language: str,
        source_language: str | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.model = model.strip()
        self.target_language = target_language.strip()
        self.source_language = (source_language or "").strip()

    def translate_segments(
        self, segments: list[SubtitleSegment]
    ) -> TranslatedSubtitleResult:
        self._validate_config(segments)
        translated_blocks: list[str] = []
        for start_index, batch in self._iter_segment_batches(segments):
            payload = self._build_request_payload(segments, start_index, batch)
            response_payload = self._post_json(payload)
            self._raise_for_truncated_response(response_payload)
            translated_text = self._extract_message_content(response_payload)
            translated_blocks.extend(
                self._extract_translated_blocks(
                    translated_text, expected_segments=batch
                )
            )

        translated_segments = [
            SubtitleSegment(
                index=segment.index,
                start=segment.start,
                end=segment.end,
                text=translated_block,
            )
            for segment, translated_block in zip(segments, translated_blocks)
        ]

        return TranslatedSubtitleResult(
            segments=translated_segments,
            srt_text=self._render_srt(translated_segments),
            vtt_text=self._render_vtt(translated_segments),
            txt_text=self._render_txt(translated_segments),
        )

    def _validate_config(self, segments: list[SubtitleSegment]) -> None:
        if not self.api_key:
            raise SubtitleTranslationError("translation API key must not be empty")
        if not self.base_url:
            raise SubtitleTranslationError("translation base URL must not be empty")
        if not self.model:
            raise SubtitleTranslationError("translation model must not be empty")
        if not self.target_language:
            raise SubtitleTranslationError(
                "translation target language must not be empty"
            )
        if not segments:
            raise SubtitleTranslationError("translation requires at least one segment")

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_obj = request.Request(
            url=self._chat_completions_url(),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with request.urlopen(request_obj, timeout=60) as response:
                raw = response.read()
        except error.HTTPError as exc:
            message = self._format_http_error(exc)
            if payload.get("response_format") and self._is_response_format_error(message):
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                return self._post_json(fallback_payload)
            raise SubtitleTranslationError(message) from exc
        except error.URLError as exc:
            message = self._redact_secrets(f"translation request failed: {exc}")
            raise SubtitleTranslationError(message) from exc

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubtitleTranslationError(
                "translation response was not valid JSON"
            ) from exc

        if not isinstance(parsed, dict):
            raise SubtitleTranslationError("translation response must be a JSON object")
        return parsed

    def _build_request_payload(
        self,
        all_segments: list[SubtitleSegment],
        start_index: int,
        batch: list[SubtitleSegment],
    ) -> dict[str, Any]:
        source_language = self.source_language or "auto-detected source language"
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Translate each subtitle segment into {self.target_language}. "
                        f"The source language is {source_language}. "
                        "Return only valid JSON with this exact schema: "
                        '{"translations":[{"index":1,"text":"translated subtitle text"}]}. '
                        "Return exactly one translation for each input segment, "
                        "in the same order, using the same index values. "
                        "Use the full transcript context only to understand surrounding meaning; "
                        "translate only the segment text values. "
                        "Do not add timestamps, numbering, markdown, URLs, platform names, "
                        "explanations, or unrelated content. "
                        "Preserve line breaks inside each text value."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_language": self.target_language,
                            "source_language": self.source_language or "auto",
                            "full_transcript": self._build_context_transcript(
                                all_segments, start_index, len(batch)
                            ),
                            "segments": [
                                self._format_segment_payload(segment)
                                for segment in batch
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _format_http_error(self, exc: error.HTTPError) -> str:
        status_code = exc.code
        reason = str(exc.msg).strip()
        message = f"translation request failed with HTTP {status_code}"
        if reason:
            message = f"{message} {reason}"

        provider_message = self._http_error_body_message(exc)
        if provider_message:
            message = f"{message}: {provider_message}"

        return self._redact_secrets(message)

    @classmethod
    def _http_error_body_message(cls, exc: error.HTTPError) -> str:
        raw_body = exc.read()
        if not raw_body:
            return ""

        body_text = raw_body.decode("utf-8", errors="replace").strip()
        if not body_text:
            return ""

        try:
            parsed_body = json.loads(body_text)
        except json.JSONDecodeError:
            return cls._truncate_provider_message(body_text)

        provider_message = cls._extract_provider_message(parsed_body)
        if provider_message:
            return cls._truncate_provider_message(provider_message)
        return cls._truncate_provider_message(body_text)

    @staticmethod
    def _extract_provider_message(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""

        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            for key in ("message", "detail", "error_description", "code", "type"):
                value = error_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()

        for key in ("message", "detail", "error_description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _truncate_provider_message(message: str) -> str:
        normalized = " ".join(message.split())
        if len(normalized) <= 1000:
            return normalized
        return f"{normalized[:997]}..."

    def _redact_secrets(self, message: str) -> str:
        if not self.api_key:
            return message
        return message.replace(self.api_key, "[redacted]")

    @staticmethod
    def _is_response_format_error(message: str) -> bool:
        normalized = message.lower()
        return (
            "response_format" in normalized
            or "response format" in normalized
            or "json_object" in normalized
            or "unsupported parameter" in normalized
        )

    @staticmethod
    def _extract_message_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise SubtitleTranslationError("translation response did not contain text")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise SubtitleTranslationError("translation response did not contain text")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise SubtitleTranslationError("translation response did not contain text")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise SubtitleTranslationError("translation response did not contain text")
        return content.strip()

    @staticmethod
    def _raise_for_truncated_response(payload: dict[str, Any]) -> None:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return
        if first_choice.get("finish_reason") == "length":
            raise SubtitleTranslationError(
                "translation response was truncated by the provider; "
                "try a larger-context model or shorter input"
            )

    @staticmethod
    def _extract_translated_blocks(
        translated_text: str, *, expected_segments: list[SubtitleSegment]
    ) -> list[str]:
        normalized = translated_text.replace("\r\n", "\n").strip()
        if not normalized:
            raise SubtitleTranslationError("translation response did not contain text")

        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            parsed = SubtitleTranslationService._parse_embedded_json_object(
                normalized, exc
            )

        if not isinstance(parsed, dict):
            raise SubtitleTranslationError(
                "translation response JSON must be an object"
            )

        translations = parsed.get("translations")
        if not isinstance(translations, list):
            raise SubtitleTranslationError(
                "translation response JSON must contain a translations array"
            )

        expected_count = len(expected_segments)
        if len(translations) != expected_count:
            raise SubtitleTranslationError(
                "translation response segment count mismatch: "
                f"expected {expected_count}, received {len(translations)}"
            )

        translated_blocks: list[str] = []
        for position, (translation, expected_segment) in enumerate(
            zip(translations, expected_segments), start=1
        ):
            translated_blocks.append(
                SubtitleTranslationService._extract_translation_text(
                    translation,
                    expected_index=expected_segment.index,
                    position=position,
                    source_text=expected_segment.text,
                )
            )
        return translated_blocks

    @staticmethod
    def _extract_translation_text(
        translation: Any, *, expected_index: int, position: int, source_text: str
    ) -> str:
        if not isinstance(translation, dict):
            raise SubtitleTranslationError(
                f"translation response item {position} must be an object"
            )

        index = translation.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            raise SubtitleTranslationError(
                f"translation response item {position} must contain integer index"
            )
        if index != expected_index:
            raise SubtitleTranslationError(
                "translation response index mismatch at item "
                f"{position}: expected {expected_index}, received {index}"
            )

        text = translation.get("text")
        if not isinstance(text, str):
            raise SubtitleTranslationError(
                f"translation response item {position} must contain string text"
            )

        cleaned = text.replace("\r\n", "\n").strip()
        if not cleaned:
            raise SubtitleTranslationError(
                f"translation response item {position} text must not be empty"
            )
        SubtitleTranslationService._validate_translated_text(
            cleaned, source_text=source_text, position=position
        )
        return cleaned

    @staticmethod
    def _format_segment_payload(segment: SubtitleSegment) -> dict[str, Any]:
        return {
            "index": segment.index,
            "text": segment.text,
        }

    @staticmethod
    def _build_full_transcript(segments: list[SubtitleSegment]) -> str:
        return "\n".join(
            segment.text.strip() for segment in segments if segment.text.strip()
        )

    @classmethod
    def _build_context_transcript(
        cls,
        all_segments: list[SubtitleSegment],
        start_index: int,
        batch_size: int,
    ) -> str:
        if batch_size >= len(all_segments):
            return cls._build_full_transcript(all_segments)

        context_start = max(0, start_index - TRANSLATION_CONTEXT_SEGMENTS)
        context_end = min(
            len(all_segments),
            start_index + batch_size + TRANSLATION_CONTEXT_SEGMENTS,
        )
        context_text = cls._build_full_transcript(all_segments[context_start:context_end])
        if len(context_text) <= MAX_TRANSLATION_CONTEXT_CHARS:
            return context_text
        return f"{context_text[:MAX_TRANSLATION_CONTEXT_CHARS - 3].rstrip()}..."

    @staticmethod
    def _iter_segment_batches(
        segments: list[SubtitleSegment],
    ) -> list[tuple[int, list[SubtitleSegment]]]:
        batches: list[tuple[int, list[SubtitleSegment]]] = []
        current_batch: list[SubtitleSegment] = []
        current_start = 0
        current_chars = 0
        for position, segment in enumerate(segments):
            segment_chars = len(segment.text)
            would_exceed_count = len(current_batch) >= MAX_TRANSLATION_SEGMENTS_PER_REQUEST
            would_exceed_chars = (
                current_batch
                and current_chars + segment_chars > MAX_TRANSLATION_SOURCE_CHARS_PER_REQUEST
            )
            if would_exceed_count or would_exceed_chars:
                batches.append((current_start, current_batch))
                current_batch = []
                current_start = position
                current_chars = 0

            current_batch.append(segment)
            current_chars += segment_chars

        if current_batch:
            batches.append((current_start, current_batch))
        return batches

    @staticmethod
    def _parse_embedded_json_object(
        normalized_text: str, original_error: json.JSONDecodeError
    ) -> dict[str, Any]:
        fenced_text = normalized_text
        if fenced_text.startswith("```"):
            lines = fenced_text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fenced_text = "\n".join(lines).strip()
            try:
                parsed = json.loads(fenced_text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, dict):
                    return parsed

        raise SubtitleTranslationError(
            "translation response content was not valid JSON"
        ) from original_error

    @staticmethod
    def _validate_translated_text(
        translated_text: str, *, source_text: str, position: int
    ) -> None:
        if "\ufffd" in translated_text:
            raise SubtitleTranslationError(
                f"translation response item {position} contains invalid replacement characters"
            )
        if TIMESTAMP_PATTERN.search(translated_text):
            raise SubtitleTranslationError(
                f"translation response item {position} contains a timestamp; expected text only"
            )

        source_urls = set(URL_PATTERN.findall(source_text))
        translated_urls = set(URL_PATTERN.findall(translated_text))
        unexpected_urls = translated_urls - source_urls
        if unexpected_urls:
            raise SubtitleTranslationError(
                f"translation response item {position} contains an unexpected URL"
            )

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, milliseconds = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    @classmethod
    def _render_srt(cls, segments: list[SubtitleSegment]) -> str:
        lines: list[str] = []
        for segment in segments:
            lines.extend(
                [
                    str(segment.index),
                    f"{cls._format_srt_time(segment.start)} --> {cls._format_srt_time(segment.end)}",
                    segment.text,
                    "",
                ]
            )
        return "\n".join(lines).rstrip()

    @classmethod
    def _render_vtt(cls, segments: list[SubtitleSegment]) -> str:
        lines = ["WEBVTT", ""]
        for segment in segments:
            start = cls._format_srt_time(segment.start).replace(",", ".")
            end = cls._format_srt_time(segment.end).replace(",", ".")
            lines.extend([str(segment.index), f"{start} --> {end}", segment.text, ""])
        return "\n".join(lines).rstrip()

    @staticmethod
    def _render_txt(segments: list[SubtitleSegment]) -> str:
        return "\n".join(segment.text for segment in segments).rstrip()
