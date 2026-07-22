"""Reporting: present the top matches per job posting and save them to disk."""

from __future__ import annotations

import html
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
            lines.append(f"{rank}. {result.resume.name} - score {result.score}/100")
            if result.comment:
                lines.append(f"   {result.comment}")
    return "\n".join(lines)


def print_report(top_matches: dict[str, list[MatchResult]]) -> None:
    """Print the top-N resumes for each job posting to the console."""
    print(format_report(top_matches))


def write_report(top_matches: dict[str, list[MatchResult]], results_dir: Path) -> Path:
    """Save the run's results as HTML, text, and JSON. Returns the HTML path."""
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
                {"resume": r.resume.name, "score": r.score, "comment": r.comment}
                for r in results
            ],
        }
        for job_source, results in top_matches.items()
    ]
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    html_path = results_dir / f"run_{stamp}.html"
    html_path.write_text(format_html_report(top_matches, stamp), encoding="utf-8")

    return html_path


def _score_class(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 50:
        return "medium"
    return "weak"


def _resume_link(result: MatchResult) -> str:
    """A file:// URI to the resume so it opens when clicked in a browser."""
    try:
        return result.resume.path.resolve().as_uri()
    except (ValueError, OSError):
        return ""


def format_html_report(top_matches: dict[str, list[MatchResult]], stamp: str) -> str:
    """Render the results as a self-contained, theme-aware HTML page."""
    total_jobs = len(top_matches)
    total_scored = sum(len(r) for r in top_matches.values())

    sections: list[str] = []
    for job_source, results in top_matches.items():
        job_title = results[0].job.title if results else job_source
        if not results:
            sections.append(
                f'<details class="job"><summary>'
                f'<span class="job-title">{html.escape(job_title)}</span>'
                f'<span class="summary-meta">no resumes scored</span>'
                f'</summary><p class="empty">No resumes were scored for this job.</p></details>'
            )
            continue

        best = results[0].score
        rows: list[str] = []
        for rank, result in enumerate(results, start=1):
            link = _resume_link(result)
            name = html.escape(result.resume.name)
            name_html = f'<a href="{html.escape(link)}">{name}</a>' if link else name
            comment = html.escape(result.comment) if result.comment else ""
            rows.append(
                f'<li class="match">'
                f'<span class="rank">{rank}</span>'
                f'<div class="match-body">'
                f'<div class="match-head">'
                f'<span class="resume-name">{name_html}</span>'
                f'<span class="badge {_score_class(result.score)}">{result.score}<small>/100</small></span>'
                f'</div>'
                f'{f"<p class=comment>{comment}</p>" if comment else ""}'
                f'</div></li>'
            )
        sections.append(
            f'<details class="job" open>'
            f'<summary>'
            f'<span class="job-title">{html.escape(job_title)}</span>'
            f'<span class="summary-meta">'
            f'<span class="count">{len(results)} matches</span>'
            f'<span class="badge {_score_class(best)} small">top {best}</span>'
            f'</span>'
            f'</summary>'
            f'<div class="source">{html.escape(job_source)}</div>'
            f'<ol class="matches">{"".join(rows)}</ol>'
            f'</details>'
        )

    return _HTML_TEMPLATE.format(
        stamp=html.escape(stamp),
        total_jobs=total_jobs,
        total_scored=total_scored,
        sections="\n".join(sections),
    )


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resume Matcher results - {stamp}</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --text: #1c2128; --muted: #6a737d;
    --border: #e1e4e8; --accent: #2f6feb;
    --strong-bg: #dafbe1; --strong-fg: #1a7f37;
    --medium-bg: #fff3cd; --medium-fg: #9a6700;
    --weak-bg: #ffe9e9; --weak-fg: #b42318;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0d1117; --card: #161b22; --text: #e6edf3; --muted: #8b949e;
      --border: #30363d; --accent: #4c8dff;
      --strong-bg: #14351f; --strong-fg: #5ce27f;
      --medium-bg: #3a2f0b; --medium-fg: #e3b341;
      --weak-bg: #3a1a1a; --weak-fg: #ff7b72;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 2rem 1rem; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 820px; margin: 0 auto; }}
  header {{ margin-bottom: 1.75rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .35rem; }}
  .subtitle {{ color: var(--muted); font-size: .9rem; }}
  details.job {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    margin-bottom: .85rem; overflow: hidden;
  }}
  summary {{
    cursor: pointer; list-style: none; padding: 1rem 1.15rem;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  }}
  summary::-webkit-details-marker {{ display: none; }}
  summary::before {{
    content: "\\25B8"; color: var(--muted); margin-right: .1rem;
    transition: transform .15s ease; display: inline-block;
  }}
  details[open] summary::before {{ transform: rotate(90deg); }}
  .job-title {{ font-weight: 600; flex: 1; }}
  .summary-meta {{ display: flex; align-items: center; gap: .6rem; color: var(--muted); font-size: .85rem; }}
  .source {{ padding: 0 1.15rem; color: var(--muted); font-size: .8rem; font-family: ui-monospace, monospace; }}
  ol.matches {{ list-style: none; margin: .4rem 0 .6rem; padding: 0; }}
  li.match {{ display: flex; gap: .85rem; padding: .7rem 1.15rem; border-top: 1px solid var(--border); }}
  .rank {{
    flex: none; width: 1.6rem; height: 1.6rem; border-radius: 50%;
    background: var(--bg); border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: .8rem; color: var(--muted); font-weight: 600;
  }}
  .match-body {{ flex: 1; min-width: 0; }}
  .match-head {{ display: flex; align-items: center; justify-content: space-between; gap: .75rem; }}
  .resume-name a {{ color: var(--accent); text-decoration: none; word-break: break-all; }}
  .resume-name a:hover {{ text-decoration: underline; }}
  .comment {{ margin: .3rem 0 0; color: var(--muted); font-size: .9rem; }}
  .badge {{
    flex: none; font-weight: 700; font-size: .95rem; border-radius: 999px;
    padding: .15rem .6rem; white-space: nowrap;
  }}
  .badge small {{ font-weight: 500; opacity: .7; }}
  .badge.small {{ font-size: .75rem; padding: .1rem .5rem; }}
  .badge.strong {{ background: var(--strong-bg); color: var(--strong-fg); }}
  .badge.medium {{ background: var(--medium-bg); color: var(--medium-fg); }}
  .badge.weak {{ background: var(--weak-bg); color: var(--weak-fg); }}
  .empty {{ padding: 0 1.15rem 1rem; color: var(--muted); }}
  footer {{ margin-top: 2rem; text-align: center; color: var(--muted); font-size: .8rem; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Resume Matcher results</h1>
    <div class="subtitle">{total_jobs} job(s) &middot; {total_scored} resume match(es) &middot; {stamp}</div>
  </header>
  {sections}
  <footer>Generated locally by resume_matcher. Click a resume name to open the file.</footer>
</div>
</body>
</html>
"""
