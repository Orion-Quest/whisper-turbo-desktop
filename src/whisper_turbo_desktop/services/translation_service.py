from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

MAX_TRANSLATION_SEGMENTS_PER_REQUEST = 40
MAX_TRANSLATION_SOURCE_CHARS_PER_REQUEST = 7000
TRANSLATION_CONTEXT_SEGMENTS = 3
MAX_TRANSLATION_CONTEXT_CHARS = 5000
TRANSLATION_REQUEST_ATTEMPTS = 3
TRANSLATION_REQUEST_TIMEOUT_SECONDS = 60
TRANSLATION_REQUEST_RETRY_DELAYS_SECONDS = (0.4, 1.2)
TRANSLATION_MODEL_OUTPUT_ATTEMPTS = 2
TIMESTAMP_PATTERN = re.compile(r"\b\d{2}:\d{2}:\d{2}[,.]\d{3}\b")
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
LATIN_WORD_PATTERN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:'[A-Za-zÀ-ÖØ-öø-ÿ]+)*")
COMMON_ENGLISH_CONTRACTION_PATTERN = re.compile(
    r"(?i)^(?:[a-z]+(?:n't|'(?:ll|re|ve|d|m|s))|ma'am|o'clock|twas|y'all)$"
)
LOW_CONFIDENCE_ASR_QUALITY = "low_confidence_asr"
NORMAL_SOURCE_QUALITY = "normal"
LOW_CONFIDENCE_ASR_GUIDANCE = (
    "Use context to repair this likely ASR error; if still unclear, "
    "translate as an unclear-audio marker."
)
TRANSIENT_REQUEST_EXCEPTIONS = (
    error.URLError,
    TimeoutError,
    socket.timeout,
    ssl.SSLError,
    ConnectionResetError,
    ConnectionAbortedError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
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
            translated_blocks.extend(
                self._translate_batch_with_output_retries(segments, start_index, batch)
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

    def _translate_batch_with_output_retries(
        self,
        all_segments: list[SubtitleSegment],
        start_index: int,
        batch: list[SubtitleSegment],
    ) -> list[str]:
        previous_error = ""
        for attempt in range(1, TRANSLATION_MODEL_OUTPUT_ATTEMPTS + 1):
            payload = self._build_request_payload(
                all_segments,
                start_index,
                batch,
                retry_reason=previous_error,
            )
            response_payload = self._post_json(payload)
            self._raise_for_truncated_response(response_payload)
            translated_text = self._extract_message_content(response_payload)
            try:
                return self._extract_translated_blocks(
                    translated_text, expected_segments=batch
                )
            except SubtitleTranslationError as exc:
                previous_error = self._retry_reason_from_translation_error(exc)
                if attempt >= TRANSLATION_MODEL_OUTPUT_ATTEMPTS:
                    raise
        raise SubtitleTranslationError("translation response did not contain text")

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
        try:
            raw = self._send_json_request(payload)
        except error.HTTPError as exc:
            message = self._format_http_error(exc)
            if payload.get("response_format") and self._is_response_format_error(message):
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                return self._post_json(fallback_payload)
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

    def _send_json_request(self, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_exception: BaseException | None = None
        for attempt in range(1, TRANSLATION_REQUEST_ATTEMPTS + 1):
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
                with request.urlopen(
                    request_obj, timeout=TRANSLATION_REQUEST_TIMEOUT_SECONDS
                ) as response:
                    return response.read()
            except error.HTTPError:
                raise
            except TRANSIENT_REQUEST_EXCEPTIONS as exc:
                if not self._is_retryable_request_exception(exc):
                    message = self._format_non_retryable_request_error(exc)
                    raise SubtitleTranslationError(message) from exc
                last_exception = exc
                if attempt >= TRANSLATION_REQUEST_ATTEMPTS:
                    break
                self._sleep_before_retry(attempt)

        message = self._format_transient_request_error(
            last_exception, TRANSLATION_REQUEST_ATTEMPTS
        )
        raise SubtitleTranslationError(message) from last_exception

    @staticmethod
    def _is_retryable_request_exception(exc: BaseException) -> bool:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return False
        if isinstance(exc, error.URLError):
            reason = exc.reason
            if isinstance(reason, ssl.SSLCertVerificationError):
                return False
            if isinstance(reason, TRANSIENT_REQUEST_EXCEPTIONS):
                return True
            return isinstance(reason, OSError)
        return True

    @staticmethod
    def _sleep_before_retry(attempt: int) -> None:
        delay_index = min(
            max(attempt - 1, 0), len(TRANSLATION_REQUEST_RETRY_DELAYS_SECONDS) - 1
        )
        time.sleep(TRANSLATION_REQUEST_RETRY_DELAYS_SECONDS[delay_index])

    def _build_request_payload(
        self,
        all_segments: list[SubtitleSegment],
        start_index: int,
        batch: list[SubtitleSegment],
        retry_reason: str = "",
    ) -> dict[str, Any]:
        source_language = self.source_language or "auto-detected source language"
        retry_instruction = ""
        if retry_reason:
            retry_instruction = (
                "Previous response failed validation: "
                f"{retry_reason}. Retry the same input and fix that problem. "
            )
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
                        "Use natural localized dialogue subtitle wording, not word-by-word output. "
                        "Preserve speaker intent, jokes, register, and short subtitle rhythm. "
                        "The source may contain Whisper ASR mistakes. Use context to repair obvious "
                        "recognition errors before translating. Segments marked "
                        "source_quality=low_confidence_asr are likely garbled; if the meaning is still "
                        "unclear, output a concise target-language unclear-audio marker instead of "
                        "phonetic transliteration or literal nonsense. "
                        "Do not translate English contraction or grammar fragments literally; localize "
                        "their function in the dialogue. "
                        "Translate ordinary source-language words; keep only unavoidable proper names, "
                        "brand names, filenames, URLs, or technical tokens untranslated. "
                        "Do not output mojibake, invalid replacement characters, mixed-script garbage, "
                        "timestamps, numbering, markdown, URLs that were not in the source, platform names, "
                        "explanations, or unrelated content. "
                        "Preserve line breaks inside each text value. "
                        f"{retry_instruction}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_language": self.target_language,
                            "source_language": self.source_language or "auto",
                            "unclear_audio_marker": self._unclear_audio_marker(),
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

    def _format_transient_request_error(
        self, exc: BaseException | None, attempts: int
    ) -> str:
        original_error = (
            self._technical_error_detail(exc)
            if exc is not None
            else "unknown connection error"
        )
        normalized = original_error.lower()
        if (
            "unexpected_eof_while_reading" in normalized
            or "eof occurred in violation of protocol" in normalized
        ):
            cause = "TLS connection closed while reading the translation response"
        elif "timed out" in normalized or "timeout" in normalized:
            cause = "translation request timed out"
        elif "remote end closed connection" in normalized:
            cause = "remote server closed the translation connection"
        else:
            cause = "translation API connection failed"

        message = (
            f"translation request failed after {attempts} attempts: {cause}. "
            "Check the API endpoint, proxy or VPN, network stability, and provider status. "
            f"Original error: {original_error}"
        )
        return self._redact_secrets(message)

    def _format_non_retryable_request_error(self, exc: BaseException) -> str:
        original_error = self._technical_error_detail(exc)
        normalized = original_error.lower()
        if "certificate" in normalized or "cert" in normalized:
            cause = "translation API TLS certificate verification failed"
            guidance = (
                "Check the API endpoint URL, proxy certificate, system trust store, "
                "or use a provider endpoint with a valid HTTPS certificate."
            )
        else:
            cause = "translation API connection failed"
            guidance = "Check the API endpoint, network, proxy, and provider status."
        return self._redact_secrets(
            f"translation request failed: {cause}. {guidance} Original error: {original_error}"
        )

    @staticmethod
    def _technical_error_detail(exc: BaseException) -> str:
        if isinstance(exc, error.URLError):
            reason = exc.reason
            if isinstance(reason, BaseException):
                return f"{reason.__class__.__name__}: {reason}"
            return str(reason)
        return f"{exc.__class__.__name__}: {exc}"

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
    def _retry_reason_from_translation_error(exc: SubtitleTranslationError) -> str:
        return SubtitleTranslationService._truncate_provider_message(str(exc))

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

    def _extract_translated_blocks(
        self, translated_text: str, *, expected_segments: list[SubtitleSegment]
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
                self._extract_translation_text(
                    translation,
                    expected_index=expected_segment.index,
                    position=position,
                    source_text=expected_segment.text,
                )
            )
        return translated_blocks

    def _extract_translation_text(
        self, translation: Any, *, expected_index: int, position: int, source_text: str
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
        self._validate_translated_text(
            cleaned, source_text=source_text, position=position
        )
        return cleaned

    def _format_segment_payload(self, segment: SubtitleSegment) -> dict[str, Any]:
        source_quality = self._source_text_quality(segment.text)
        payload = {
            "index": segment.index,
            "text": segment.text,
            "source_quality": source_quality,
        }
        if source_quality == LOW_CONFIDENCE_ASR_QUALITY:
            payload["translation_guidance"] = LOW_CONFIDENCE_ASR_GUIDANCE
        return payload

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

    def _validate_translated_text(
        self, translated_text: str, *, source_text: str, position: int
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

        self._validate_semantic_translation_quality(
            translated_text, source_text=source_text, position=position
        )
        self._validate_target_script_quality(translated_text, position=position)

    def _validate_semantic_translation_quality(
        self, translated_text: str, *, source_text: str, position: int
    ) -> None:
        if (
            self._target_script_profile() == "chinese"
            and self._is_english_contraction_drill(source_text)
            and self._looks_like_literal_chinese_grammar_translation(translated_text)
        ):
            raise SubtitleTranslationError(
                f"translation response item {position} is an overly literal "
                "translation of an English grammar fragment"
            )

        if (
            self._source_text_quality(source_text) == LOW_CONFIDENCE_ASR_QUALITY
            and self._looks_like_phonetic_output_for_noisy_source(translated_text)
        ):
            raise SubtitleTranslationError(
                f"translation response item {position} appears to be phonetic "
                "transliteration of low-confidence ASR instead of a translation "
                "or unclear-audio marker"
            )

    def _validate_target_script_quality(
        self, translated_text: str, *, position: int
    ) -> None:
        profile = self._target_script_profile()
        if profile == "chinese":
            self._validate_chinese_translation_quality(
                translated_text, position=position
            )
        elif profile == "japanese":
            self._validate_cjk_translation_quality(
                translated_text,
                position=position,
                script_name="Japanese",
                target_count=self._count_japanese_script(translated_text),
            )
        elif profile == "korean":
            self._validate_cjk_translation_quality(
                translated_text,
                position=position,
                script_name="Korean",
                target_count=self._count_korean_script(translated_text),
            )

    def _target_script_profile(self) -> str:
        normalized = self.target_language.casefold()
        if any(
            token in normalized
            for token in (
                "chinese",
                "mandarin",
                "cantonese",
                "simplified",
                "traditional",
                "中文",
                "汉语",
                "漢語",
                "简体",
                "繁体",
                "zh",
            )
        ):
            return "chinese"
        if any(
            token in normalized
            for token in ("japanese", "日本語", "日语", "日文", "ja")
        ):
            return "japanese"
        if any(
            token in normalized
            for token in ("korean", "한국어", "韩语", "韓語", "ko")
        ):
            return "korean"
        return ""

    def _unclear_audio_marker(self) -> str:
        profile = self._target_script_profile()
        if profile == "chinese":
            return "（听不清）"
        if profile == "japanese":
            return "（聞き取れません）"
        if profile == "korean":
            return "(잘 들리지 않음)"
        return "[unclear audio]"

    @staticmethod
    def _is_english_contraction_drill(source_text: str) -> bool:
        normalized = source_text.casefold()
        required_tokens = ("should've", "would've", "hadn't", "ma'am", "twas")
        return sum(token in normalized for token in required_tokens) >= 3

    @staticmethod
    def _looks_like_literal_chinese_grammar_translation(translated_text: str) -> bool:
        literal_terms = (
            "本来可以",
            "本可以",
            "本来会",
            "本会",
            "没有",
            "女士",
            "曾经",
            "从前",
        )
        return sum(term in translated_text for term in literal_terms) >= 2

    def _source_text_quality(self, source_text: str) -> str:
        text = source_text.strip()
        if not text:
            return LOW_CONFIDENCE_ASR_QUALITY
        if "\ufffd" in text:
            return LOW_CONFIDENCE_ASR_QUALITY
        if self._contains_obvious_mojibake(text):
            return LOW_CONFIDENCE_ASR_QUALITY
        if self._looks_like_latin_asr_noise(text):
            return LOW_CONFIDENCE_ASR_QUALITY
        return NORMAL_SOURCE_QUALITY

    @staticmethod
    def _contains_obvious_mojibake(text: str) -> bool:
        mojibake_markers = ("Ã", "Â", "ð", "�")
        return any(marker in text for marker in mojibake_markers)

    def _looks_like_latin_asr_noise(self, text: str) -> bool:
        if not self._source_allows_latin_noise_checks():
            return False

        words = LATIN_WORD_PATTERN.findall(text)
        if len(words) < 2:
            return False

        suspicious_words = sum(
            1 for word in words if self._is_suspicious_latin_asr_word(word)
        )
        return suspicious_words >= 2

    def _source_allows_latin_noise_checks(self) -> bool:
        normalized = self.source_language.casefold()
        if not normalized:
            return True
        latin_language_names = (
            "english",
            "spanish",
            "french",
            "german",
            "italian",
            "portuguese",
        )
        latin_language_codes = {"en", "es", "fr", "de", "it", "pt"}
        return normalized in latin_language_codes or any(
            name in normalized for name in latin_language_names
        )

    @classmethod
    def _is_suspicious_latin_asr_word(cls, word: str) -> bool:
        normalized = word.casefold().strip("'")
        if not normalized:
            return False

        if "'" in word and not COMMON_ENGLISH_CONTRACTION_PATTERN.match(normalized):
            if word.endswith("'") or word.count("'") >= 2:
                return True

        has_non_ascii_latin = any(ord(character) > 127 for character in normalized)
        if has_non_ascii_latin:
            return True

        ascii_letters = re.sub(r"[^a-z]", "", normalized)
        if len(ascii_letters) < 4:
            return False
        has_repeated_consonant_cluster = bool(
            re.search(
                r"([bcdfghjklmnpqrstvwxyz])\1[bcdfghjklmnpqrstvwxyz]",
                ascii_letters,
            )
        )
        has_suspicious_terminal = bool(
            re.search(r"[bcdfghjklmnpqrstvwxyz]{3}[iy]{2}$", ascii_letters)
        )
        return len(ascii_letters) <= 7 and (
            has_repeated_consonant_cluster or has_suspicious_terminal
        )

    def _looks_like_phonetic_output_for_noisy_source(self, translated_text: str) -> bool:
        if self._unclear_audio_marker() in translated_text:
            return False

        profile = self._target_script_profile()
        if profile == "japanese":
            kana_count = self._count_kana_script(translated_text)
            cjk_count = self._count_cjk_unified(translated_text)
            return kana_count >= 6 and kana_count > max(cjk_count * 2, 4) and (
                "・" in translated_text or cjk_count == 0
            )
        return False

    def _validate_chinese_translation_quality(
        self, translated_text: str, *, position: int
    ) -> None:
        cjk_count = self._count_cjk_unified(translated_text)
        latin_count = self._count_latin_letters(translated_text)
        unexpected_script_count = (
            self._count_cyrillic_script(translated_text)
            + self._count_korean_script(translated_text)
            + self._count_kana_script(translated_text)
        )
        if unexpected_script_count:
            raise SubtitleTranslationError(
                f"translation response item {position} contains unexpected non-Chinese script"
            )
        if latin_count >= 8 and cjk_count == 0:
            raise SubtitleTranslationError(
                f"translation response item {position} does not look like Chinese subtitle text"
            )
        if latin_count >= 14 and latin_count > max(cjk_count * 2, 10):
            raise SubtitleTranslationError(
                f"translation response item {position} still contains too much source-language text"
            )

    def _validate_cjk_translation_quality(
        self,
        translated_text: str,
        *,
        position: int,
        script_name: str,
        target_count: int,
    ) -> None:
        latin_count = self._count_latin_letters(translated_text)
        cyrillic_count = self._count_cyrillic_script(translated_text)
        if cyrillic_count:
            raise SubtitleTranslationError(
                f"translation response item {position} contains unexpected Cyrillic script"
            )
        if latin_count >= 8 and target_count == 0:
            raise SubtitleTranslationError(
                f"translation response item {position} does not look like {script_name} subtitle text"
            )
        if latin_count >= 14 and latin_count > max(target_count * 2, 10):
            raise SubtitleTranslationError(
                f"translation response item {position} still contains too much source-language text"
            )

    @staticmethod
    def _count_latin_letters(text: str) -> int:
        return sum(
            1
            for character in text
            if "A" <= character <= "Z" or "a" <= character <= "z"
        )

    @staticmethod
    def _count_cjk_unified(text: str) -> int:
        return sum(1 for character in text if "\u4e00" <= character <= "\u9fff")

    @staticmethod
    def _count_kana_script(text: str) -> int:
        return sum(
            1
            for character in text
            if "\u3040" <= character <= "\u30ff" or "\uff66" <= character <= "\uff9f"
        )

    @classmethod
    def _count_japanese_script(cls, text: str) -> int:
        return cls._count_cjk_unified(text) + cls._count_kana_script(text)

    @staticmethod
    def _count_korean_script(text: str) -> int:
        return sum(
            1
            for character in text
            if "\uac00" <= character <= "\ud7af"
            or "\u1100" <= character <= "\u11ff"
            or "\u3130" <= character <= "\u318f"
        )

    @staticmethod
    def _count_cyrillic_script(text: str) -> int:
        return sum(1 for character in text if "\u0400" <= character <= "\u04ff")

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
