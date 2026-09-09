"""Central configuration for resume_matcher.

Values can be overridden via environment variables or CLI flags.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # --- Local LLM server (Unsloth Desktop) ---
    # Unsloth Desktop serves models over an OpenAI-compatible API; any server
    # speaking that API works. Copy the URL from Unsloth Desktop's server panel
    # if it differs from this default (include the /v1 suffix).
    llm_base_url: str = os.environ.get("RM_LLM_BASE_URL", "http://localhost:8888/v1")
    # Local servers usually ignore the key, but the OpenAI client requires one.
    llm_api_key: str = os.environ.get("RM_LLM_API_KEY", "local")
    # Preferred model. Matched case-insensitively as a substring of the ids the
    # server reports, so it need not be the exact id. The supported Gemma 4
    # QAT variants, by hardware (see README for details):
    #   gemma-4-e4b-it-qat      ~6 GB   - small VRAM, or CPU/RAM
    #   gemma-4-12b-it-qat      ~12 GB  - the default
    #   gemma-4-26b-a4b-it-qat  ~24 GB  - best quality, MoE so still fast
    llm_model: str = os.environ.get("RM_LLM_MODEL", "gemma-4-12b")
    llm_temperature: float = 0.1
    # Generous budget: reasoning-tuned models emit thinking tokens before the
    # answer, and those count against this limit.
    llm_max_tokens: int = 2048

    # Per-request timeout in seconds. Scoring calls are quick; transcription
    # of image resumes can take minutes on partial GPU offload.
    llm_timeout: float = 300.0

    # Print raw model replies and finish reasons for each scoring call.
    verbose: bool = False

    # Image-based resumes (scanned PDFs, .png/.jpg) are OCR-ed with Tesseract
    # automatically when it is installed. This flag enables the fallback of
    # transcribing them with the model's vision input instead - much slower
    # (minutes per page on partial GPU offload) but needs no extra install.
    ocr: bool = False

    # --- Input locations ---
    # Folder containing resumes (.pdf, .doc, .docx).
    resumes_dir: Path = field(default_factory=lambda: Path("resumes"))
    # Folder containing job postings saved from email (.txt or .eml files).
    # For live inbox watching instead of a folder, see email_watch.py.
    jobs_dir: Path = field(default_factory=lambda: Path("jobs"))

    # --- Matching ---
    top_n: int = 5
    # How many scoring requests to keep in flight at once. The server batches
    # concurrent requests, so this raises throughput a lot on GPU. Keep it at
    # or below the server's parallel-request limit, and make sure the context
    # length covers concurrency x per-request tokens (see README).
    concurrency: int = int(os.environ.get("RM_CONCURRENCY", "4"))

    # --- Output ---
    # Run results (text + JSON) are written here; the folder is gitignored.
    results_dir: Path = field(default_factory=lambda: Path("results"))

    # --- Outlook inbox watching (Windows desktop Outlook via COM) ---
    # See outlook.py / email_watch.py. Polls the inbox for unread job emails,
    # matches each against all resumes, and emails the results back.
    # Only process unread emails whose subject contains this text (case-
    # insensitive). Empty means every unread email is treated as a job posting.
    outlook_subject_filter: str = os.environ.get("RM_SUBJECT_FILTER", "")
    # Where to send results. Empty means send them to the monitored mailbox
    # itself (the signed-in Outlook account), so you receive the matches.
    result_recipient: str = os.environ.get("RM_RESULT_TO", "")
    # Seconds between inbox polls.
    poll_interval: int = int(os.environ.get("RM_POLL_INTERVAL", "60"))
    # Mark a job email as read once its results have been sent.
    mark_processed_read: bool = True

    # --- Email ingestion, file-based (see email_ingest.py) ---
    imap_host: str = os.environ.get("RM_IMAP_HOST", "")
    imap_user: str = os.environ.get("RM_IMAP_USER", "")
    imap_password: str = os.environ.get("RM_IMAP_PASSWORD", "")
    imap_folder: str = os.environ.get("RM_IMAP_FOLDER", "INBOX")
