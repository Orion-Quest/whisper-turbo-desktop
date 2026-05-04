from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

_INDEX_PATTERN = re.compile(r"^\d+$")
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}$"
)


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
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.model = model.strip()
        self.target_language = target_language.strip()

    def translate_segments(
        self, segments: list[SubtitleSegment]
    ) -> TranslatedSubtitleResult:
        self._validate_config(segments)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"Translate each subtitle block into {self.target_language}. "
                        "Return exactly one translated block for each input subtitle, "
                        "in the same order. Preserve line breaks inside a block. "
                        "Do not add explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        self._format_segment(segment) for segment in segments
                    ),
                },
            ],
            "temperature": 0,
        }

        response_payload = self._post_json(payload)
        translated_text = self._extract_message_content(response_payload)
        translated_blocks = self._extract_translated_blocks(
            translated_text, expected_count=len(segments)
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
        except error.URLError as exc:
            raise SubtitleTranslationError(f"translation request failed: {exc}") from exc

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SubtitleTranslationError(
                "translation response was not valid JSON"
            ) from exc

        if not isinstance(parsed, dict):
            raise SubtitleTranslationError("translation response must be a JSON object")
        return parsed

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

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
    def _extract_translated_blocks(
        translated_text: str, *, expected_count: int
    ) -> list[str]:
        normalized = translated_text.replace("\r\n", "\n").strip()
        if not normalized:
            raise SubtitleTranslationError("translation response did not contain text")

        blocks = [block for block in re.split(r"\n\s*\n", normalized) if block.strip()]
        if len(blocks) == expected_count:
            return [SubtitleTranslationService._clean_block(block) for block in blocks]

        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if len(lines) == expected_count:
            return [SubtitleTranslationService._clean_block(line) for line in lines]

        if expected_count == 1:
            return [SubtitleTranslationService._clean_block(normalized)]

        raise SubtitleTranslationError(
            f"translation response did not contain {expected_count} subtitle block(s)"
        )

    @staticmethod
    def _clean_block(block: str) -> str:
        lines = [line.rstrip() for line in block.replace("\r\n", "\n").splitlines()]
        if lines and _INDEX_PATTERN.fullmatch(lines[0].strip()):
            lines = lines[1:]
        if lines and _TIMESTAMP_PATTERN.fullmatch(lines[0].strip()):
            lines = lines[1:]
        cleaned = "\n".join(line.rstrip() for line in lines).strip()
        if not cleaned:
            raise SubtitleTranslationError(
                "translation block did not contain subtitle text"
            )
        return cleaned

    @staticmethod
    def _format_segment(segment: SubtitleSegment) -> str:
        start = SubtitleTranslationService._format_srt_time(segment.start)
        end = SubtitleTranslationService._format_srt_time(segment.end)
        return f"{segment.index}\n{start} --> {end}\n{segment.text}"

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
