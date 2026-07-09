"""Central configuration for resume_matcher.

Values can be overridden via environment variables or CLI flags.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # --- Local LLM (LM Studio) ---
    # LM Studio exposes an OpenAI-compatible server, by default at this URL.
    llm_base_url: str = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
    # LM Studio ignores the API key but the OpenAI client requires one.
    llm_api_key: str = os.environ.get("LMSTUDIO_API_KEY", "lm-studio")
    # Model identifier as loaded in LM Studio.
    llm_model: str = os.environ.get("LMSTUDIO_MODEL", "google/gemma-4-26b-a4b-qat")
    llm_temperature: float = 0.1
    # Generous budget: reasoning-tuned models emit thinking tokens before the
    # answer, and those count against this limit.
    llm_max_tokens: int = 2048

    # Print raw model replies and finish reasons for each scoring call.
    verbose: bool = False

    # --- Input locations ---
    # Folder containing resumes (.pdf, .doc, .docx).
    resumes_dir: Path = field(default_factory=lambda: Path("resumes"))
    # Folder containing job postings saved from email (.txt or .eml files).
    # TODO: replace/augment with live IMAP fetching (see email_ingest.py).
    jobs_dir: Path = field(default_factory=lambda: Path("jobs"))

    # --- Matching ---
    top_n: int = 5

    # --- Output ---
    # Run results (text + JSON) are written here; the folder is gitignored.
    results_dir: Path = field(default_factory=lambda: Path("results"))

    # --- Email ingestion (stub — see email_ingest.py) ---
    imap_host: str = os.environ.get("RM_IMAP_HOST", "")
    imap_user: str = os.environ.get("RM_IMAP_USER", "")
    imap_password: str = os.environ.get("RM_IMAP_PASSWORD", "")
    imap_folder: str = os.environ.get("RM_IMAP_FOLDER", "INBOX")
