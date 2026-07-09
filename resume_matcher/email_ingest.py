"""Job posting ingestion.

Step 1 of the workflow: the user receives job postings by email.

Scaffolding approach: for now, job postings are read from a local folder
(one posting per file, .txt or .eml). Live IMAP fetching is stubbed out
below and can be filled in later without changing the rest of the pipeline.
"""

from __future__ import annotations

import email
import email.policy
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JobPosting:
    """A single job posting extracted from an email or file."""

    source: str  # filename or message id
    title: str   # subject line or filename stem
    body: str    # plain-text job description


def load_jobs_from_folder(jobs_dir: Path) -> list[JobPosting]:
    """Load job postings from a folder of .txt / .eml files."""
    postings: list[JobPosting] = []
    for path in sorted(jobs_dir.glob("*")):
        if path.suffix.lower() == ".txt":
            postings.append(
                JobPosting(source=path.name, title=path.stem, body=path.read_text(encoding="utf-8"))
            )
        elif path.suffix.lower() == ".eml":
            postings.append(_parse_eml(path))
    return postings


def _parse_eml(path: Path) -> JobPosting:
    """Extract subject and plain-text body from a saved email message."""
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    body_part = msg.get_body(preferencelist=("plain",))
    body = body_part.get_content() if body_part else ""
    return JobPosting(source=path.name, title=msg.get("Subject", path.stem), body=body)


def fetch_jobs_from_imap(host: str, user: str, password: str, folder: str = "INBOX") -> list[JobPosting]:
    """Fetch unread job-posting emails from an IMAP mailbox.

    TODO(scaffolding): implement with imaplib —
      1. Connect with imaplib.IMAP4_SSL(host) and log in.
      2. Select `folder`, search for unseen messages (optionally filter by
         sender/subject keywords like "job", "opening", "role").
      3. Parse each message with email.message_from_bytes and extract the
         plain-text body, as in _parse_eml above.
      4. Return a list of JobPosting objects.
    """
    raise NotImplementedError("IMAP ingestion is not implemented yet; use load_jobs_from_folder.")
