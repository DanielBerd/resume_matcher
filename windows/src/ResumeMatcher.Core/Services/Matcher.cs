using ResumeMatcher.Core.Models;

namespace ResumeMatcher.Core.Services;

/// <summary>How far along a run is, reported to the UI as it happens.</summary>
public sealed record MatchProgress(int Done, int Total, string Message)
{
    public double Fraction => Total == 0 ? 0 : (double)Done / Total;
}

/// <summary>Scores every resume against every job and keeps the best per job.</summary>
public sealed class Matcher(AppSettings settings, LlmClient client)
{
    /// <summary>
    /// Run the whole job x resume matrix.
    ///
    /// Requests run concurrently, but each still carries exactly one job and one
    /// resume — concurrency changes only how many are in flight, never what the
    /// model sees. Resumes are scored in parallel within a job; jobs run one
    /// after another so progress stays readable.
    /// </summary>
    public async Task<Dictionary<JobPosting, List<MatchResult>>> RunAsync(
        IReadOnlyList<JobPosting> jobs,
        IReadOnlyList<Resume> resumes,
        IProgress<MatchProgress>? progress = null,
        CancellationToken ct = default)
    {
        var results = new Dictionary<JobPosting, List<MatchResult>>();
        var total = jobs.Count * resumes.Count;
        var done = 0;

        foreach (var job in jobs)
        {
            ct.ThrowIfCancellationRequested();
            progress?.Report(new MatchProgress(done, total, $"Job: {job.Title}"));

            var scored = new List<MatchResult>();
            using var gate = new SemaphoreSlim(Math.Max(1, settings.Concurrency));

            var tasks = resumes.Select(async resume =>
            {
                await gate.WaitAsync(ct).ConfigureAwait(false);
                try
                {
                    var result = await client.ScoreAsync(job, resume, ct).ConfigureAwait(false);
                    lock (scored)
                    {
                        scored.Add(result);
                        var n = Interlocked.Increment(ref done);
                        progress?.Report(new MatchProgress(n, total,
                            $"[{n}/{total}] {resume.Name} scored {result.Score}"));
                    }
                }
                catch (Exception e) when (e is LlmException)
                {
                    // One bad resume must not sink the run; it is reported and skipped.
                    var n = Interlocked.Increment(ref done);
                    progress?.Report(new MatchProgress(n, total, $"[{n}/{total}] {resume.Name} failed: {e.Message}"));
                }
                finally
                {
                    gate.Release();
                }
            });

            await Task.WhenAll(tasks).ConfigureAwait(false);

            // Ties break by name so two runs of the same data agree.
            results[job] = scored
                .OrderByDescending(r => r.Score)
                .ThenBy(r => r.Resume.Name, StringComparer.OrdinalIgnoreCase)
                .Take(settings.TopN)
                .ToList();
        }

        progress?.Report(new MatchProgress(total, total, "Done"));
        return results;
    }
}
