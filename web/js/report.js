// Builds the results report. The same markup is used for the in-page results
// and for the standalone file the Download button saves.

const escape = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const band = (score) => (score >= 75 ? 'good' : score >= 50 ? 'mid' : 'low');

/** The <details> blocks, shared by the page and the downloadable file. */
export function resultsMarkup(results) {
  const blocks = [];
  for (const [job, matches] of results) {
    const rows = matches.length === 0
      ? '<div class="empty">No resumes could be scored for this job.</div>'
      : `<table>
  <tr><th></th><th>Score</th><th>Resume</th><th>Comment</th></tr>
${matches.map((m, i) => `  <tr>
    <td class="rank">${i + 1}</td>
    <td class="score"><span class="badge ${band(m.score)}">${m.score}</span></td>
    <td class="name">${escape(m.resume.name)}</td>
    <td>${escape(m.comment)}</td>
  </tr>`).join('\n')}
</table>`;

    blocks.push(`<details open>
  <summary><span>${escape(job.title)}</span>
  <span class="count">${matches.length} match${matches.length === 1 ? '' : 'es'}</span></summary>
  <div class="source">${escape(job.source)}</div>
${rows}
</details>`);
  }
  return blocks.join('\n');
}

/** A standalone HTML file, styled independently of the app's own stylesheet. */
export function standaloneReport(results, stamp) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resume Matcher — ${escape(stamp)}</title>
<style>
  :root {
    --bg:#f6f8fa; --card:#fff; --ink:#1f2328; --muted:#656d76;
    --line:#d8dee4; --good:#1a7f37; --mid:#9a6700; --low:#b42318;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#0d1117; --card:#161b22; --ink:#e6edf3; --muted:#8b949e;
      --line:#30363d; --good:#3fb950; --mid:#d29922; --low:#f85149;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;padding:2rem 1rem;background:var(--bg);color:var(--ink);
       font:15px/1.55 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}
  .wrap{max-width:60rem;margin:0 auto}
  h1{font-size:1.5rem;margin:0 0 .25rem}
  .stamp{color:var(--muted);font-size:.85rem;margin-bottom:2rem}
  details{background:var(--card);border:1px solid var(--line);border-radius:10px;
          margin-bottom:1rem;overflow:hidden}
  summary{cursor:pointer;padding:.9rem 1.15rem;font-weight:600;display:flex;
          justify-content:space-between;gap:1rem;align-items:center}
  summary::-webkit-details-marker{display:none}
  .count{color:var(--muted);font-weight:400;font-size:.85rem}
  .source{padding:0 1.15rem .6rem;color:var(--muted);font-size:.8rem;
          font-family:ui-monospace,Consolas,monospace}
  table{width:100%;border-collapse:collapse}
  th,td{padding:.6rem 1.15rem;text-align:left;border-top:1px solid var(--line)}
  th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
  td.rank{color:var(--muted);width:2.5rem}
  td.score{width:5rem}
  td.name{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
  .badge{display:inline-block;min-width:2.75rem;text-align:center;padding:.15rem .5rem;
         border-radius:999px;font-weight:600;font-size:.85rem;color:#fff}
  .good{background:var(--good)}.mid{background:var(--mid)}.low{background:var(--low)}
  .empty{padding:1rem 1.15rem;color:var(--muted)}
</style>
</head>
<body><div class="wrap">
<h1>Resume Matcher</h1>
<div class="stamp">Run ${escape(stamp)}</div>
${resultsMarkup(results)}
</div></body></html>
`;
}

export function timestamp() {
  const d = new Date(), p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`;
}
