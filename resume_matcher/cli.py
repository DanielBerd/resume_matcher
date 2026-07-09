"""Command-line entry point.

Usage:
    python -m resume_matcher --jobs jobs/ --resumes resumes/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config
from .documents import load_resumes
from .email_ingest import load_jobs_from_folder
from .matcher import run
from .report import print_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resume_matcher",
        description="Score a folder of resumes against job postings using a local Gemma model in LM Studio.",
    )
    parser.add_argument("--jobs", type=Path, default=None, help="Folder with job postings (.txt/.eml)")
    parser.add_argument("--resumes", type=Path, default=None, help="Folder with resumes (.pdf/.doc/.docx)")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Use the bundled example jobs and resumes (examples/jobs, examples/resumes) "
        "instead of the real input folders",
    )
    parser.add_argument("--top", type=int, default=None, help="Number of top matches to report (default 5)")
    parser.add_argument("--model", default=None, help="Model name as loaded in LM Studio")
    parser.add_argument("--base-url", default=None, help="LM Studio server URL (default http://localhost:1234/v1)")
    args = parser.parse_args(argv)

    config = Config()
    if args.test_mode:
        # Bundled sample data, resolved relative to the repo so this works from any cwd.
        examples_dir = Path(__file__).resolve().parent.parent / "examples"
        config.jobs_dir = examples_dir / "jobs"
        config.resumes_dir = examples_dir / "resumes"
    if args.jobs:
        config.jobs_dir = args.jobs
    if args.resumes:
        config.resumes_dir = args.resumes
    if args.top:
        config.top_n = args.top
    if args.model:
        config.llm_model = args.model
    if args.base_url:
        config.llm_base_url = args.base_url

    if not config.jobs_dir.is_dir():
        print(f"error: jobs folder not found: {config.jobs_dir}", file=sys.stderr)
        return 1
    if not config.resumes_dir.is_dir():
        print(f"error: resumes folder not found: {config.resumes_dir}", file=sys.stderr)
        return 1

    jobs = load_jobs_from_folder(config.jobs_dir)
    if not jobs:
        print(f"error: no job postings (.txt/.eml) found in {config.jobs_dir}", file=sys.stderr)
        return 1

    resumes = load_resumes(config.resumes_dir)
    if not resumes:
        print(f"error: no resumes (.pdf/.doc/.docx) found in {config.resumes_dir}", file=sys.stderr)
        return 1

    print(f"Loaded {len(jobs)} job posting(s) and {len(resumes)} resume(s).")
    print(f"Model: {config.llm_model} @ {config.llm_base_url}")

    top_matches = run(config, jobs, resumes)
    print_report(top_matches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
