"""Prompting and score parsing for the resume-vs-job match.

Step 3 of the workflow: for each (job posting, resume) pair, ask Gemma to
score the match 0-100 with an optional one-sentence comment.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .documents import Resume
from .email_ingest import JobPosting

if TYPE_CHECKING:
    from .llm_client import LocalLLM

SYSTEM_PROMPT = (
    "You are a recruiting assistant. You will be given a job posting and one "
    "candidate resume. Rate how well the resume matches the job on a scale of "
    "0 to 100, where 0 is no match at all and 100 is a perfect match. "
    "Respond with ONLY a JSON object of the form: "
    '{"score": <integer 0-100>, "comment": "<one short sentence>"}'
)

USER_PROMPT_TEMPLATE = """JOB POSTING:
{job}

RESUME:
{resume}

Rate the match. Respond with only the JSON object."""


@dataclass
class MatchResult:
    """The model's rating of one resume against one job posting."""

    job: JobPosting
    resume: Resume
    score: int
    comment: str


def score_resume(llm: "LocalLLM", job: JobPosting, resume: Resume) -> MatchResult:
    """Ask the local model to score one resume against one job posting."""
    prompt = USER_PROMPT_TEMPLATE.format(job=job.body, resume=resume.text)
    reply = llm.complete(SYSTEM_PROMPT, prompt)
    score, comment = parse_reply(reply)
    return MatchResult(job=job, resume=resume, score=score, comment=comment)


def parse_reply(reply: str) -> tuple[int, str]:
    """Parse the model's reply into (score, comment).

    Prefers the requested JSON format, but falls back to grabbing the first
    number in the reply since local models don't always follow instructions.
    """
    # Drop thinking blocks emitted by reasoning-tuned models before parsing,
    # so a number inside the reasoning isn't mistaken for the score.
    reply = re.sub(r"<think(?:ing)?>.*?(?:</think(?:ing)?>|$)", "", reply, flags=re.DOTALL)

    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            score = int(data.get("score", 0))
            comment = str(data.get("comment", "")).strip()
            return _clamp(score), comment
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    number = re.search(r"\b(\d{1,3})\b", reply)
    if number:
        return _clamp(int(number.group(1))), reply.strip()[:200]

    return 0, f"Unparseable reply: {reply.strip()[:200]}"


def _clamp(score: int) -> int:
    return max(0, min(100, score))
