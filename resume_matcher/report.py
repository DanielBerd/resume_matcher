"""Reporting: present the top matches per job posting to the user."""

from __future__ import annotations

from .scoring import MatchResult


def print_report(top_matches: dict[str, list[MatchResult]]) -> None:
    """Print the top-N resumes for each job posting to the console."""
    for job_source, results in top_matches.items():
        if not results:
            print(f"\n=== {job_source}: no resumes scored ===")
            continue
        job_title = results[0].job.title
        print(f"\n=== Top {len(results)} matches for: {job_title} ({job_source}) ===")
        for rank, result in enumerate(results, start=1):
            print(f"{rank}. {result.resume.name} — score {result.score}/100")
            if result.comment:
                print(f"   {result.comment}")
