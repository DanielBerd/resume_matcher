"""Reporting: present the top matches per job posting and save them to disk."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .scoring import MatchResult


def format_report(top_matches: dict[str, list[MatchResult]]) -> str:
    """Render the top-N results per job as human-readable text."""
    lines: list[str] = []
    for job_source, results in top_matches.items():
        if not results:
            lines.append(f"\n=== {job_source}: no resumes scored ===")
            continue
        job_title = results[0].job.title
        lines.append(f"\n=== Top {len(results)} matches for: {job_title} ({job_source}) ===")
        for rank, result in enumerate(results, start=1):
            lines.append(f"{rank}. {result.resume.display_name} - score {result.score}/100")
            if result.comment:
                lines.append(f"   {result.comment}")
    return "\n".join(lines)


def print_report(top_matches: dict[str, list[MatchResult]]) -> None:
    """Print the top-N resumes for each job posting to the console."""
    print(format_report(top_matches))


def write_report(top_matches: dict[str, list[MatchResult]], results_dir: Path) -> Path:
    """Save the run's results as text and JSON. Returns the text file path."""
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    text_path = results_dir / f"run_{stamp}.txt"
    text_path.write_text(format_report(top_matches).lstrip("\n") + "\n", encoding="utf-8")

    json_path = results_dir / f"run_{stamp}.json"
    payload = [
        {
            "job_source": job_source,
            "job_title": results[0].job.title if results else None,
            "matches": [
                {
                    "resume": r.resume.name,
                    "candidate": r.resume.candidate_name or None,
                    "score": r.score,
                    "comment": r.comment,
                }
                for r in results
            ],
        }
        for job_source, results in top_matches.items()
    ]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return text_path
