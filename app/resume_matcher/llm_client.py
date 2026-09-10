"""Client for the local Gemma model served by Unsloth Desktop.

Unsloth Desktop exposes an OpenAI-compatible API, so we use the openai client
pointed at the local server. Any other OpenAI-compatible server works too.
"""

from __future__ import annotations

import base64
import mimetypes
import json
import re
import time
import urllib.error
import urllib.request

from openai import OpenAI

from .config import Config

# Unsloth Desktop answers every request with this when no model is loaded and
# points at its own (non-OpenAI) load endpoint.
NOT_LOADED_HINT = "no model loaded"
LOAD_PATH = "/inference/load"

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


def server_root(base_url: str) -> str:
    """'http://localhost:8888/v1' -> 'http://localhost:8888' (the /inference/load
    endpoint lives beside /v1, not under it)."""
    return re.sub(r"/v\d+/?$", "", base_url.rstrip("/"))


def probe_model(config: Config, timeout: float = 30.0) -> None:
    """One-token completion: raises if the server or model is not ready."""
    client = OpenAI(base_url=config.llm_base_url, api_key=config.llm_api_key, timeout=timeout)
    client.chat.completions.create(
        model=config.llm_model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
        temperature=0,
    )


def _looks_unloaded(exc: Exception) -> bool:
    text = str(exc).lower()
    return NOT_LOADED_HINT in text or LOAD_PATH in text


def _post_json(url: str, payload: dict, timeout: float) -> tuple[int, str]:
    """POST a JSON body; returns (status, body text). HTTP errors are returned,
    not raised; only connection failures raise (URLError)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def request_model_load(config: Config, timeout: float) -> None:
    """POST the server's load endpoint for the configured model.

    The exact request shape is not documented, so the obvious field names are
    tried in turn; the endpoint is tried beside /v1 first, then under it.
    Raises RuntimeError with the server's reply when none is accepted.
    """
    urls = [server_root(config.llm_base_url) + LOAD_PATH, config.llm_base_url.rstrip("/") + LOAD_PATH]
    payloads = [{"model": config.llm_model}, {"model_id": config.llm_model}, {"name": config.llm_model}]
    last = "no response"
    for url in urls:
        for payload in payloads:
            try:
                status, text = _post_json(url, payload, timeout)
            except (urllib.error.URLError, OSError) as exc:
                last = f"{url}: {exc}"
                break  # this URL is unreachable; try the next one
            if status < 300:
                return
            last = f"{url} -> {status} {text[:200]}"
            if status == 404:
                break  # wrong URL, no point trying other payloads on it
    raise RuntimeError(f"The server did not accept the load request ({last}).")


def ensure_model_loaded(config: Config, log=print, wait: float | None = None, poll: float = 2.0) -> str:
    """Make sure the configured model is ready to answer, loading it if needed.

    Returns "ready" if it already was, "loaded" if this call loaded it.
    Other failures (bad key, unreachable server, unknown model) are raised.
    """
    wait = config.llm_load_timeout if wait is None else wait
    try:
        probe_model(config)
        return "ready"
    except Exception as exc:
        if not _looks_unloaded(exc):
            raise
    log(f"Loading {config.llm_model} on the server (this can take a minute) ...")
    request_model_load(config, timeout=wait)
    deadline = time.monotonic() + wait
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            probe_model(config)
            log(f"{config.llm_model} is loaded.")
            return "loaded"
        except Exception as exc:
            if not _looks_unloaded(exc):
                raise
            last = exc
            time.sleep(poll)
    raise RuntimeError(
        f"Gave up after {int(wait)}s waiting for the server to load {config.llm_model}: {last}"
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
