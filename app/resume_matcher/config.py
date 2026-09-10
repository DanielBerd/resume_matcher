"""Central configuration for resume_matcher.

Precedence, lowest to highest:
  1. the defaults below
  2. app/settings.json (written by the GUI's Server tab;
     gitignored because it can hold an API key)
  3. RM_* environment variables
  4. command-line flags (applied by the entry points)

`Config()` gives bare defaults, which keeps tests deterministic;
`Config.load()` applies layers 2 and 3 and is what the entry points use.
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Folder layout, anchored to this file so nothing depends on the current
# working directory (double-click launchers start anywhere):
#   <project>/ResumeMatcher.pyw, README.md, resumes/, jobs/, results/
#   <project>/app/                 code, launchers, .venv, settings.json
APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent
SETTINGS_PATH = APP_DIR / "settings.json"

# Fields the GUI's Server tab manages and settings.json persists. Kept to a
# whitelist so the file never grows stale copies of unrelated settings.
SETTINGS_FIELDS = (
    "llm_mode",
    "llm_provider",
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "concurrency",
)

# Field -> environment variable.
ENV_VARS = {
    "llm_base_url": "RM_LLM_BASE_URL",
    "llm_api_key": "RM_LLM_API_KEY",
    "llm_model": "RM_LLM_MODEL",
    "concurrency": "RM_CONCURRENCY",
    "llm_timeout": "RM_LLM_TIMEOUT",
    "llm_busy_wait": "RM_LLM_BUSY_WAIT",
    "outlook_subject_filter": "RM_SUBJECT_FILTER",
    "result_recipient": "RM_RESULT_TO",
    "poll_interval": "RM_POLL_INTERVAL",
    "imap_host": "RM_IMAP_HOST",
    "imap_user": "RM_IMAP_USER",
    "imap_password": "RM_IMAP_PASSWORD",
    "imap_folder": "RM_IMAP_FOLDER",
}


@dataclass
class Config:
    # --- Model server ---
    # "local": a server on this machine (Unsloth Desktop by default) - nothing
    # leaves the computer. "hosted": a cloud API; job postings and resume text
    # are sent to it. Both speak the OpenAI-compatible API.
    llm_mode: str = "local"
    # Name of the preset the Server tab last applied (see providers.py).
    llm_provider: str = "Unsloth Desktop"
    # Copy the URL from the server's panel if it differs (include the /v1).
    llm_base_url: str = "http://localhost:8888/v1"
    # Local servers usually ignore the key, but the OpenAI client requires one.
    # For hosted APIs this is the real key.
    llm_api_key: str = "local"
    # Preferred model. For local servers this is matched case-insensitively as
    # a substring of the ids the server reports, so it need not be the exact
    # id. The supported Gemma 4 QAT variants, by hardware (details in README):
    #   gemma-4-e4b-it-qat      ~6 GB   - small VRAM, or CPU/RAM
    #   gemma-4-12b-it-qat      ~12 GB  - the default
    #   gemma-4-26b-a4b-it-qat  ~24 GB  - best quality, MoE so still fast
    llm_model: str = "gemma-4-12b"
    llm_temperature: float = 0.1
    # Generous budget: reasoning-tuned models emit thinking tokens before the
    # answer, and those count against this limit.
    llm_max_tokens: int = 2048
    # Per-request timeout in seconds. Note that with `concurrency` requests in
    # flight and a server with fewer parallel slots, a request may wait in the
    # server's queue for (concurrency / slots) x one request's time before it
    # even starts, so keep this generous. A timed-out request is never resent
    # (the server would still finish the original and the work would double).
    llm_timeout: float = 600.0
    # When the server answers "busy" (HTTP 429/503 - the request was not
    # processed), keep retrying with backoff for up to this many seconds.
    llm_busy_wait: float = 120.0
    # How long to wait for the server to load a model on request (large
    # models take a while to come off disk).
    llm_load_timeout: float = 300.0

    # Print raw model replies and finish reasons for each scoring call.
    verbose: bool = False

    # Image-based resumes (scanned PDFs, .png/.jpg) are OCR-ed with Tesseract
    # automatically when it is installed. This flag enables the fallback of
    # transcribing them with the model's vision input instead - much slower
    # (minutes per page on partial GPU offload) but needs no extra install.
    ocr: bool = False

    # --- Input locations ---
    resumes_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "resumes")
    # Job postings saved from email (.txt or .eml). For live inbox watching
    # instead of a folder, see email_watch.py.
    jobs_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "jobs")

    # --- Matching ---
    top_n: int = 5
    # How many scoring requests to keep in flight at once. The server batches
    # concurrent requests, so this raises throughput a lot on GPU. Keep it at
    # or below the server's parallel-request limit, and make sure the context
    # length covers concurrency x per-request tokens (see README).
    concurrency: int = 4

    # --- Output ---
    # Run results (HTML, text, JSON) are written here; the folder is gitignored.
    results_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "results")

    # --- Outlook inbox watching (Windows desktop Outlook via COM) ---
    # See outlook.py / email_watch.py. Polls the inbox for unread job emails,
    # matches each against all resumes, and emails the results back.
    # Only process unread emails whose subject contains this text (case-
    # insensitive). Empty means every unread email is treated as a job posting.
    outlook_subject_filter: str = ""
    # Where to send results. Empty means send them to the monitored mailbox
    # itself (the signed-in Outlook account), so you receive the matches.
    result_recipient: str = ""
    # Seconds between inbox polls.
    poll_interval: int = 60
    # Mark a job email as read once its results have been sent.
    mark_processed_read: bool = True

    # --- Email ingestion, file-based (see email_ingest.py) ---
    imap_host: str = ""
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"

    # ---------- layering ----------

    @classmethod
    def load(cls, settings_path: Path | None = None, environ: dict | None = None) -> "Config":
        """Defaults, then settings.json, then RM_* environment variables."""
        config = cls()
        config.apply_settings_file(settings_path or SETTINGS_PATH)
        config.apply_env(os.environ if environ is None else environ)
        return config

    def apply_settings_file(self, path: Path) -> bool:
        """Overlay saved settings. Missing or unreadable files are ignored."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        for name in SETTINGS_FIELDS:
            if name in data:
                self._set_typed(name, data[name])
        return True

    def apply_env(self, environ: dict) -> None:
        for name, var in ENV_VARS.items():
            if var in environ and environ[var] != "":
                self._set_typed(name, environ[var])

    def save_settings(self, path: Path | None = None) -> Path:
        """Write the Server-tab settings to settings.json."""
        path = path or SETTINGS_PATH
        data = {name: getattr(self, name) for name in SETTINGS_FIELDS}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def _set_typed(self, name: str, value) -> None:
        """Assign, coercing to the field's declared type (env values are str)."""
        current = getattr(self, name)
        try:
            if isinstance(current, bool):
                value = str(value).strip().lower() in ("1", "true", "yes", "on")
            elif isinstance(current, int):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, Path):
                value = Path(value)
            else:
                value = str(value)
        except (TypeError, ValueError):
            return  # keep the existing value rather than crash on junk
        setattr(self, name, value)

    def with_model(self, model: str) -> "Config":
        return dataclasses.replace(self, llm_model=model)

    @property
    def is_hosted(self) -> bool:
        return self.llm_mode == "hosted"
