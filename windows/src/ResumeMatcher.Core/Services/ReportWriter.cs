using System.Net;
using System.Text;
using ResumeMatcher.Core.Models;

namespace ResumeMatcher.Core.Services;

/// <summary>Writes the run's results as a standalone HTML file.</summary>
public static class ReportWriter
{
    /// <summary>Save the report and return its path. One timestamped file per run.</summary>
    public static string Write(Dictionary<JobPosting, List<MatchResult>> results, string resultsDir)
    {
        Directory.CreateDirectory(resultsDir);
        var stamp = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
        var path = Path.Combine(resultsDir, $"run_{stamp}.html");
        File.WriteAllText(path, BuildHtml(results, stamp), Encoding.UTF8);
        return path;
    }

    public static string BuildHtml(Dictionary<JobPosting, List<MatchResult>> results, string stamp)
    {
        var sb = new StringBuilder();
        sb.Append($$"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Resume Matcher - {{WebUtility.HtmlEncode(stamp)}}</title>
            <style>
              :root {
                --bg: #f6f8fa; --card: #ffffff; --ink: #1f2328; --muted: #656d76;
                --line: #d8dee4; --good: #1a7f37; --mid: #9a6700; --low: #b42318;
              }
              @media (prefers-color-scheme: dark) {
                :root {
                  --bg: #0d1117; --card: #161b22; --ink: #e6edf3; --muted: #8b949e;
                  --line: #30363d; --good: #3fb950; --mid: #d29922; --low: #f85149;
                }
              }
              * { box-sizing: border-box; }
              body {
                margin: 0; padding: 2rem 1rem; background: var(--bg); color: var(--ink);
                font: 15px/1.55 "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
              }
              .wrap { max-width: 60rem; margin: 0 auto; }
              h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
              .stamp { color: var(--muted); font-size: .85rem; margin-bottom: 2rem; }
              details {
                background: var(--card); border: 1px solid var(--line);
                border-radius: 10px; margin-bottom: 1rem; overflow: hidden;
              }
              summary {
                cursor: pointer; padding: .9rem 1.15rem; font-weight: 600;
                display: flex; justify-content: space-between; gap: 1rem; align-items: center;
              }
              summary::-webkit-details-marker { display: none; }
              .count { color: var(--muted); font-weight: 400; font-size: .85rem; }
              .source {
                padding: 0 1.15rem .6rem; color: var(--muted); font-size: .8rem;
                font-family: ui-monospace, Consolas, monospace;
              }
              table { width: 100%; border-collapse: collapse; }
              th, td { padding: .6rem 1.15rem; text-align: left; border-top: 1px solid var(--line); }
              th { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
              td.rank { color: var(--muted); width: 2.5rem; }
              td.score { width: 5rem; }
              .badge {
                display: inline-block; min-width: 2.75rem; text-align: center;
                padding: .15rem .5rem; border-radius: 999px; font-weight: 600;
                font-size: .85rem; color: #fff;
              }
              .good { background: var(--good); } .mid { background: var(--mid); } .low { background: var(--low); }
              a { color: inherit; }
              .empty { padding: 1rem 1.15rem; color: var(--muted); }
            </style>
            </head>
            <body><div class="wrap">
            <h1>Resume Matcher</h1>
            <div class="stamp">Run {{WebUtility.HtmlEncode(stamp)}}</div>

            """);

        foreach (var (job, matches) in results)
        {
            sb.Append($"""
                <details open>
                  <summary><span>{WebUtility.HtmlEncode(job.Title)}</span>
                  <span class="count">{matches.Count} match{(matches.Count == 1 ? "" : "es")}</span></summary>
                  <div class="source">{WebUtility.HtmlEncode(job.Source)}</div>

                """);

            if (matches.Count == 0)
            {
                sb.Append("  <div class=\"empty\">No resumes could be scored for this job.</div>\n");
            }
            else
            {
                sb.Append("  <table><tr><th></th><th>Score</th><th>Resume</th><th>Comment</th></tr>\n");
                for (var i = 0; i < matches.Count; i++)
                {
                    var m = matches[i];
                    var uri = new Uri(Path.GetFullPath(m.Resume.Path)).AbsoluteUri;
                    sb.Append($"""
                          <tr>
                            <td class="rank">{i + 1}</td>
                            <td class="score"><span class="badge {ScoreClass(m.Score)}">{m.Score}</span></td>
                            <td><a href="{WebUtility.HtmlEncode(uri)}">{WebUtility.HtmlEncode(m.Resume.Name)}</a></td>
                            <td>{WebUtility.HtmlEncode(m.Comment)}</td>
                          </tr>

                        """);
                }
                sb.Append("  </table>\n");
            }
            sb.Append("</details>\n");
        }

        sb.Append("</div></body></html>\n");
        return sb.ToString();
    }

    private static string ScoreClass(int score) => score >= 75 ? "good" : score >= 50 ? "mid" : "low";
}
