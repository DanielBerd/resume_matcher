"""Job posting ingestion.

Job postings are read from a local folder, one posting per file. Save the
email that carried the posting as .eml, or paste its text into a .txt file;
.md, .pdf, .docx and .doc are read too.
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


JOB_FILE_EXTENSIONS = {".txt", ".md", ".eml", ".pdf", ".docx", ".doc"}


def load_job_from_file(path: Path) -> JobPosting:
    """Load a single job posting from one file.

    Accepts plain text, saved emails, and Word/PDF documents - job postings
    arrive in all of these. Used by the GUI's drag-and-drop.
    """
    suffix = path.suffix.lower()
    if suffix == ".eml":
        return _parse_eml(path)
    if suffix in {".txt", ".md"}:
        return JobPosting(
            source=path.name, title=path.stem, body=path.read_text(encoding="utf-8", errors="replace")
        )
    if suffix in {".pdf", ".docx", ".doc"}:
        from .documents import extract_text

        return JobPosting(source=path.name, title=path.stem, body=extract_text(path))
    raise ValueError(
        f"Unsupported job posting file: {path.name} "
        f"(expected one of {', '.join(sorted(JOB_FILE_EXTENSIONS))})"
    )


def _parse_eml(path: Path) -> JobPosting:
    """Extract subject and plain-text body from a saved email message."""
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    body_part = msg.get_body(preferencelist=("plain",))
    body = body_part.get_content() if body_part else ""
    return JobPosting(source=path.name, title=msg.get("Subject", path.stem), body=body)
