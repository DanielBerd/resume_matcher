"""Orchestration: score every resume against every job and keep the top N.

Step 4 of the workflow: collect ratings per job, then report the top 5.
"""

from __future__ import annotations

from .config import Config
from .documents import Resume
from .email_ingest import JobPosting
from .llm_client import LocalLLM
from .scoring import MatchResult, score_resume


def match_job(llm: LocalLLM, job: JobPosting, resumes: list[Resume], top_n: int) -> list[MatchResult]:
    """Score all resumes against one job posting and return the top N results."""
    results: list[MatchResult] = []
    for i, resume in enumerate(resumes, start=1):
        print(f"  [{i}/{len(resumes)}] scoring {resume.name} ...")
        try:
            results.append(score_resume(llm, job, resume))
        except Exception as exc:  # keep going if one call fails
            print(f"  [warn] failed to score {resume.name}: {exc}")
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]


def run(config: Config, jobs: list[JobPosting], resumes: list[Resume]) -> dict[str, list[MatchResult]]:
    """Run the full matching pipeline. Returns {job source: top-N results}."""
    llm = LocalLLM(config)
    top_matches: dict[str, list[MatchResult]] = {}
    for job in jobs:
        print(f"\nJob: {job.title} ({job.source})")
        top_matches[job.source] = match_job(llm, job, resumes, config.top_n)
    return top_matches
