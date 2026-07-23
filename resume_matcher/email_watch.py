"""Poll an Outlook inbox for job emails, match them, and email results back.

Flow, per unread job email:
  1. Read the email as a job posting (see outlook.py).
  2. Score every resume in the resumes folder against it.
  3. Email the ranked results (HTML) back to the sender (or a configured
     recipient), then mark the email read.

`process_once` takes the mailbox as a parameter so it can be tested with a
fake in place of real Outlook; `watch` wraps it in a polling loop.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from .config import Config
from .documents import load_resumes
from .llm_client import LocalLLM
from .matcher import Progress, match_job
from .report import format_html_report


def process_once(config: Config, mailbox, llm: LocalLLM, resumes: list) -> int:
    """Handle all currently-unread job emails. Returns how many were processed."""
    jobs = mailbox.fetch_unread_jobs(config.outlook_subject_filter)
    for job in jobs:
        print(f"\nNew job email: {job.posting.title} (from {job.sender_address})")
        results = match_job(llm, job.posting, resumes, config.top_n, Progress(len(resumes)))
        top = {job.posting.source: results}
        html_body = format_html_report(top, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))

        to_addr = config.result_recipient or job.sender_address
        if not to_addr:
            print("  [warn] no recipient (sender unknown, no result_recipient set); skipping send.")
            continue
        mailbox.send_result(to_addr, f"Resume matches: {job.posting.title}", html_body)
        print(f"  Sent {len(results)} match(es) to {to_addr}")
        if config.mark_processed_read:
            mailbox.mark_read(job.entry_id)
    return len(jobs)


def watch(config: Config) -> int:
    """Load resumes once, then poll the inbox until interrupted."""
    resumes = load_resumes(config.resumes_dir)
    if not resumes:
        print(f"error: no resumes found in {config.resumes_dir}", file=sys.stderr)
        return 1

    try:
        from .outlook import OutlookMailbox

        mailbox = OutlookMailbox()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    llm = LocalLLM(config)
    print(
        f"Watching Outlook inbox every {config.poll_interval}s "
        f"({len(resumes)} resume(s), model {config.llm_model}). Press Ctrl+C to stop."
    )
    if config.outlook_subject_filter:
        print(f"Only processing unread emails with '{config.outlook_subject_filter}' in the subject.")

    while True:
        try:
            handled = process_once(config, mailbox, llm, resumes)
            if not handled:
                print(".", end="", flush=True)  # quiet heartbeat when idle
            time.sleep(config.poll_interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
        except Exception as exc:  # keep the watcher alive through transient errors
            print(f"\n[warn] poll failed: {exc}; retrying next interval.")
            time.sleep(config.poll_interval)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="resume_matcher.email_watch",
        description="Watch a Windows Outlook inbox for job emails and reply with resume matches.",
    )
    parser.add_argument("--resumes", type=str, default=None, help="Folder with resumes")
    parser.add_argument("--interval", type=int, default=None, help="Seconds between inbox polls")
    parser.add_argument("--subject-filter", default=None, help="Only process emails with this subject text")
    parser.add_argument("--to", default=None, help="Send all results here instead of replying to the sender")
    parser.add_argument("--model", default=None, help="Model name as loaded in LM Studio")
    args = parser.parse_args(argv)

    from pathlib import Path

    config = Config()
    if args.resumes:
        config.resumes_dir = Path(args.resumes)
    if args.interval:
        config.poll_interval = args.interval
    if args.subject_filter is not None:
        config.outlook_subject_filter = args.subject_filter
    if args.to:
        config.result_recipient = args.to
    if args.model:
        config.llm_model = args.model
    return watch(config)


if __name__ == "__main__":
    raise SystemExit(main())
