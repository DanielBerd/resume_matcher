"""Compare two or more LM Studio models on the same jobs and resumes.

Runs the full job x resume matrix through each model, times it, and writes a
side-by-side HTML report: per-resume scores from each model, where the top-N
rankings diverge, and how long each model took. Use it to decide whether a
smaller/faster model (e.g. Gemma 4 E4B) ranks resumes as well as a larger one
(e.g. Gemma 4 12B QAT) for your data.

The model-running part needs a live LM Studio; the report building and
rendering are pure functions so they can be tested without one.
"""

from __future__ import annotations

import html
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Config
from .documents import Resume, load_resumes
from .email_ingest import JobPosting, load_jobs_from_folder
from .llm_client import LocalLLM
from .report import _score_class
from .scoring import MatchResult, score_resume


@dataclass
class ModelRun:
    """Every score one model produced, plus how long it took."""

    model: str
    elapsed: float = 0.0
    calls: int = 0
    # job_source -> {resume_name: MatchResult}
    scores: dict[str, dict[str, MatchResult]] = field(default_factory=dict)

    def ranked(self, job_source: str) -> list[MatchResult]:
        results = list(self.scores.get(job_source, {}).values())
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def rank_of(self, job_source: str, resume_name: str) -> int | None:
        for i, r in enumerate(self.ranked(job_source), start=1):
            if r.resume.name == resume_name:
                return i
        return None


def run_model(config: Config, model: str, jobs: list[JobPosting], resumes: list[Resume]) -> ModelRun:
    """Score every resume against every job with one model, timing the whole run."""
    cfg = Config(**{**config.__dict__, "llm_model": model})
    llm = LocalLLM(cfg)
    run = ModelRun(model=model)
    total = len(jobs) * len(resumes)
    start = time.perf_counter()
    for job in jobs:
        run.scores[job.source] = {}
        for resume in resumes:
            run.calls += 1
            print(f"  [{model}] [{run.calls}/{total}] {resume.name} vs {job.source}")
            try:
                run.scores[job.source][resume.name] = score_resume(llm, job, resume)
            except Exception as exc:
                print(f"    [warn] {exc}")
        # keep going even if a job produced nothing
    run.elapsed = time.perf_counter() - start
    return run


def _agreement(runs: list[ModelRun], job_source: str, top_n: int) -> str:
    """Describe how much the models agree on the top-N for one job."""
    if len(runs) < 2:
        return ""
    tops = [[r.resume.name for r in run.ranked(job_source)[:top_n]] for run in runs]
    base = tops[0]
    shared = set(base)
    same_order = True
    for other in tops[1:]:
        shared &= set(other)
        same_order = same_order and other == base
    if same_order and len(base) == len(shared):
        return f"identical top {len(base)} (same order)"
    return f"{len(shared)} of {len(base)} shared in top {len(base)}" + (
        "" if same_order else ", different order"
    )


def format_comparison_html(
    runs: list[ModelRun], jobs: list[JobPosting], resumes: list[Resume], top_n: int, stamp: str
) -> str:
    """Render a side-by-side comparison of the model runs as HTML."""
    model_cols = "".join(f"<th>{html.escape(r.model)}</th>" for r in runs)
    delta_col = "<th>&Delta;</th>" if len(runs) == 2 else ""

    sections: list[str] = []
    for job in jobs:
        # Order rows by the first model's ranking, then any resumes it missed.
        ordered = [r.resume.name for r in runs[0].ranked(job.source)]
        for resume in resumes:
            if resume.name not in ordered:
                ordered.append(resume.name)

        rows: list[str] = []
        for name in ordered:
            cells: list[str] = []
            scores: list[int | None] = []
            for run in runs:
                mr = run.scores.get(job.source, {}).get(name)
                if mr is None:
                    cells.append('<td class="na">-</td>')
                    scores.append(None)
                    continue
                rank = run.rank_of(job.source, name)
                scores.append(mr.score)
                cells.append(
                    f'<td><span class="badge {_score_class(mr.score)}">{mr.score}</span>'
                    f'<span class="rank">#{rank}</span></td>'
                )
            if len(runs) == 2 and scores[0] is not None and scores[1] is not None:
                d = scores[1] - scores[0]
                cls = "up" if d > 0 else "down" if d < 0 else "flat"
                cells.append(f'<td class="delta {cls}">{d:+d}</td>')
            elif delta_col:
                cells.append('<td class="na">-</td>')
            rows.append(f'<tr><td class="name">{html.escape(name)}</td>{"".join(cells)}</tr>')

        agree = _agreement(runs, job.source, top_n)
        sections.append(
            f'<section><h2>{html.escape(job.title)}</h2>'
            f'<div class="agree">{html.escape(agree)}</div>'
            f'<table><thead><tr><th>Resume</th>{model_cols}{delta_col}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></section>'
        )

    # Timing summary
    timing_rows = "".join(
        f"<tr><td>{html.escape(r.model)}</td>"
        f"<td>{r.elapsed:.1f}s</td><td>{r.calls}</td>"
        f"<td>{(r.elapsed / r.calls if r.calls else 0):.2f}s</td></tr>"
        for r in runs
    )
    timing = (
        f'<section><h2>Speed</h2><table><thead><tr>'
        f"<th>Model</th><th>Total</th><th>Calls</th><th>Per call</th>"
        f"</tr></thead><tbody>{timing_rows}</tbody></table></section>"
    )

    return _COMPARE_TEMPLATE.format(stamp=html.escape(stamp), body=timing + "".join(sections))


def compare(config: Config, model_names: list[str]) -> Path:
    """Run the comparison and write an HTML report. Returns its path."""
    jobs = load_jobs_from_folder(config.jobs_dir)
    resumes = load_resumes(config.resumes_dir)
    if not jobs or not resumes:
        raise SystemExit(f"error: need jobs in {config.jobs_dir} and resumes in {config.resumes_dir}")

    runs = [run_model(config, m, jobs, resumes) for m in model_names]

    config.results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = config.results_dir / f"compare_{stamp}.html"
    out.write_text(format_comparison_html(runs, jobs, resumes, config.top_n, stamp), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="resume_matcher.compare",
        description="Compare LM Studio models on the same jobs/resumes, side by side.",
    )
    parser.add_argument("models", nargs="+", help="Two or more model names as loaded in LM Studio")
    parser.add_argument("--test-mode", action="store_true", help="Use the bundled examples/")
    parser.add_argument("--jobs", type=Path, default=None)
    parser.add_argument("--resumes", type=Path, default=None)
    parser.add_argument("--base-url", default=None, help="LM Studio server URL")
    args = parser.parse_args(argv)

    config = Config()
    if args.test_mode:
        examples = Path(__file__).resolve().parent.parent / "examples"
        config.jobs_dir, config.resumes_dir = examples / "jobs", examples / "resumes"
    if args.jobs:
        config.jobs_dir = args.jobs
    if args.resumes:
        config.resumes_dir = args.resumes
    if args.base_url:
        config.llm_base_url = args.base_url

    out = compare(config, args.models)
    print(f"\nComparison written to {out}")
    return 0


_COMPARE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Model comparison - {stamp}</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --text:#1c2128; --muted:#6a737d; --border:#e1e4e8;
    --strong-bg:#dafbe1; --strong-fg:#1a7f37; --medium-bg:#fff3cd; --medium-fg:#9a6700;
    --weak-bg:#ffe9e9; --weak-fg:#b42318; --up:#1a7f37; --down:#b42318;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:#0d1117; --card:#161b22; --text:#e6edf3; --muted:#8b949e; --border:#30363d;
      --strong-bg:#14351f; --strong-fg:#5ce27f; --medium-bg:#3a2f0b; --medium-fg:#e3b341;
      --weak-bg:#3a1a1a; --weak-fg:#ff7b72; --up:#5ce27f; --down:#ff7b72;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:2rem 1rem; background:var(--bg); color:var(--text);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:900px; margin:0 auto; }}
  h1 {{ font-size:1.6rem; margin:0 0 .3rem; }}
  .sub {{ color:var(--muted); font-size:.9rem; margin-bottom:1.5rem; }}
  section {{ background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:1rem 1.15rem; margin-bottom:1rem; overflow-x:auto; }}
  h2 {{ font-size:1.1rem; margin:.2rem 0 .1rem; }}
  .agree {{ color:var(--muted); font-size:.85rem; margin-bottom:.6rem; }}
  table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
  th,td {{ text-align:left; padding:.45rem .6rem; border-bottom:1px solid var(--border); }}
  th {{ color:var(--muted); font-weight:600; }}
  td.name {{ font-family:ui-monospace,monospace; font-size:.82rem; word-break:break-all; }}
  .badge {{ font-weight:700; border-radius:999px; padding:.1rem .5rem; }}
  .badge.strong {{ background:var(--strong-bg); color:var(--strong-fg); }}
  .badge.medium {{ background:var(--medium-bg); color:var(--medium-fg); }}
  .badge.weak {{ background:var(--weak-bg); color:var(--weak-fg); }}
  .rank {{ color:var(--muted); font-size:.75rem; margin-left:.4rem; }}
  .delta {{ font-weight:700; }}
  .delta.up {{ color:var(--up); }} .delta.down {{ color:var(--down); }} .delta.flat {{ color:var(--muted); }}
  td.na {{ color:var(--muted); }}
</style></head><body><div class="wrap">
<h1>Model comparison</h1>
<div class="sub">{stamp} &middot; score <span class="rank">#rank</span> shown per model; &Delta; is the second model minus the first</div>
{body}
</div></body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
