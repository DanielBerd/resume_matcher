"""Client for the local Gemma model served by Unsloth Desktop.

Unsloth Desktop exposes an OpenAI-compatible API, so we use the openai client
pointed at the local server. Any other OpenAI-compatible server works too.
"""

from __future__ import annotations

import base64
import mimetypes
import time

from openai import OpenAI

from .config import Config

# Unsloth Desktop answers every request with this while no model is loaded.
# Its own load endpoint is internal to the app (JWT-protected), so a client
# cannot load a model itself; with "Switch model by request" enabled the
# server loads whatever model a request names.
NOT_LOADED_HINT = "no model loaded"
AUTO_SWITCH_HINT = (
    "In Unsloth Desktop either load the model in the app, or turn on "
    "Settings > API > \"Switch model by request\" so it loads models automatically."
)

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

    def ensure_loaded(self, log=print) -> str:
        """Load the configured model on the server if it is not already loaded."""
        return ensure_model_loaded(self.config, log=log)

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


def probe_model(config: Config, timeout: float | None = None) -> None:
    """One-token completion: raises if the server or model is not ready.

    The timeout defaults to the load timeout because, with model switching
    enabled, the server may hold this very request while it loads the model.
    """
    timeout = config.llm_load_timeout if timeout is None else timeout
    client = OpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=timeout)
    client.chat.completions.create(
        model=config.llm_model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
        temperature=0,
    )


def _looks_unloaded(exc: Exception) -> bool:
    return NOT_LOADED_HINT in str(exc).lower()


def ensure_model_loaded(config: Config, log=print, wait: float = 15.0, poll: float = 3.0) -> str:
    """Make sure the configured model answers, giving the server a chance to
    load it on request.

    Returns "ready" if it answered at once, "loaded" if it came up during the
    short wait (a server that loads asynchronously). Raises a RuntimeError
    naming the Unsloth setting to enable when the server refuses to load it,
    and re-raises any other failure (bad key, unreachable server, ...).
    """
    try:
        probe_model(config)
        return "ready"
    except Exception as exc:
        if not _looks_unloaded(exc):
            raise
    log(f"{config.llm_model} is not loaded; waiting for the server to load it ...")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(poll)
        try:
            probe_model(config)
            log(f"{config.llm_model} is loaded.")
            return "loaded"
        except Exception as exc:
            if not _looks_unloaded(exc):
                raise
    raise RuntimeError(
        f"The server has no model loaded and did not load {config.llm_model} on request. "
        + AUTO_SWITCH_HINT
    )


def list_models(config: Config) -> list[str]:
    """Return the model ids available on the local model server."""
    client = OpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=10)
    return [model.id for model in client.models.list()]


def _reasoning_content(message) -> str | None:
    """Pull reasoning text out of non-standard response fields, if present."""
    value = getattr(message, "reasoning_content", None)
    if not value and message.model_extra:
        value = message.model_extra.get("reasoning_content") or message.model_extra.get("reasoning")
    return value
