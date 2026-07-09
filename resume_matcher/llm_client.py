"""Client for the local Gemma model served by LM Studio.

LM Studio exposes an OpenAI-compatible API (default http://localhost:1234/v1),
so we use the openai client pointed at the local server.
"""

from __future__ import annotations

import base64
import mimetypes

from openai import OpenAI

from .config import Config

TRANSCRIBE_PROMPT = (
    "Transcribe all text in this resume image to plain text. Preserve the "
    "reading order and section structure. Output only the transcribed text, "
    "with no commentary."
)


class LocalLLM:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            timeout=config.llm_timeout,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a single chat completion request and return the text reply."""
        response = self.client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.llm_temperature,
            max_tokens=self.config.llm_max_tokens,
        )
        choice = response.choices[0]
        content = choice.message.content or ""

        if not content.strip():
            # Some chat templates put the model's output in a separate
            # reasoning field instead of content; fall back to it.
            content = _reasoning_content(choice.message) or ""

        if self.config.verbose:
            print(f"  [debug] finish_reason={choice.finish_reason} raw reply: {content!r}")

        if not content.strip():
            raise RuntimeError(
                f"Model returned an empty reply (finish_reason={choice.finish_reason}). "
                "If finish_reason is 'length', the model spent its token budget on "
                "reasoning before answering - raise llm_max_tokens in config.py."
            )
        return content

    def transcribe_image(self, image: bytes, mime_type: str = "image/png") -> str:
        """Transcribe one resume page image to text using the model's vision input.

        Each page is its own stateless request, and the returned text is later
        sent to a fresh scoring call - the image never shares context with
        other resumes.
        """
        data_url = f"data:{mime_type};base64,{base64.b64encode(image).decode()}"
        response = self.client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=self.config.llm_max_tokens,
        )
        return response.choices[0].message.content or ""


def guess_mime_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "image/png"


def list_models(config: Config) -> list[str]:
    """Return the model ids available on the LM Studio server."""
    client = OpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=10)
    return [model.id for model in client.models.list()]


def _reasoning_content(message) -> str | None:
    """Pull reasoning text out of non-standard response fields, if present."""
    value = getattr(message, "reasoning_content", None)
    if not value and message.model_extra:
        value = message.model_extra.get("reasoning_content") or message.model_extra.get("reasoning")
    return value
