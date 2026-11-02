// Scores every resume against every job and keeps the best per job.

/** Running totals for the speed line in the log. */
function newStats() {
  return { calls: 0, promptTokens: 0, completionTokens: 0, requestMs: 0, wallMs: 0 };
}

/**
 * Two different speeds, because with requests in flight at once they are not
 * the same number and only one of them is the useful one:
 *
 *  - per call: completion tokens / that request's own wall time. It includes
 *    queueing and prompt processing, so it understates pure decode speed, and
 *    it drops as concurrency rises even while the server gets faster overall.
 *  - throughput: all completion tokens / the run's wall time. This is what
 *    actually gets the job done, and it is the one to watch when tuning.
 */
function speeds(stats) {
  const perCall = stats.requestMs > 0
    ? (stats.completionTokens / (stats.requestMs / 1000)) : 0;
  const throughput = stats.wallMs > 0
    ? (stats.completionTokens / (stats.wallMs / 1000)) : 0;
  return { perCall, throughput };
}

export function formatSummary(stats) {
  if (stats.calls === 0) return 'No requests completed.';
  const { perCall, throughput } = speeds(stats);
  const seconds = (stats.wallMs / 1000).toFixed(1);

  if (stats.completionTokens === 0) {
    // The server did not report usage; time is all we can honestly show.
    return `${stats.calls} request(s) in ${seconds}s ` +
           `(${(stats.requestMs / stats.calls / 1000).toFixed(1)}s each on average). ` +
           'The server reported no token usage, so no tok/s.';
  }

  return `${stats.calls} request(s) in ${seconds}s · ` +
         `${stats.completionTokens} completion + ${stats.promptTokens} prompt tokens · ` +
         `${throughput.toFixed(1)} tok/s throughput, ${perCall.toFixed(1)} tok/s per call`;
}

/**
 * Run the whole job x resume matrix.
 *
 * Requests run concurrently, but each still carries exactly one job and one
 * resume — concurrency changes only how many are in flight, never what the
 * model sees. Resumes run in parallel within a job; jobs run one after another
 * so the log stays readable.
 */
export async function run(client, jobs, resumes, { topN, concurrency }, onProgress, signal) {
  const results = new Map();
  const stats = newStats();
  const total = jobs.length * resumes.length;
  const startedAt = performance.now();
  let done = 0;

  for (const job of jobs) {
    signal?.throwIfAborted();
    onProgress?.({ done, total, message: `Job: ${job.title}` });

    const scored = [];
    const queue = [...resumes];

    const worker = async () => {
      for (;;) {
        const resume = queue.shift();
        if (!resume) return;
        try {
          const result = await client.score(job, resume, signal);
          scored.push(result);

          const s = result.stats ?? {};
          stats.calls += 1;
          stats.promptTokens += s.promptTokens ?? 0;
          stats.completionTokens += s.completionTokens ?? 0;
          stats.requestMs += s.ms ?? 0;

          done += 1;
          onProgress?.({ done, total, message: `[${done}/${total}] ${resume.name} scored ${result.score}${callSpeed(s)}` });
        } catch (e) {
          if (signal?.aborted) throw e;
          // One bad resume must not sink the run.
          done += 1;
          onProgress?.({ done, total, message: `[${done}/${total}] ${resume.name} failed: ${e.message}` });
        }
      }
    };

    await Promise.all(Array.from({ length: Math.max(1, concurrency) }, worker));

    // Ties break by name so two runs of the same data agree.
    scored.sort((a, b) => b.score - a.score || a.resume.name.localeCompare(b.resume.name));
    results.set(job, scored.slice(0, topN));
  }

  stats.wallMs = performance.now() - startedAt;
  onProgress?.({ done: total, total, message: formatSummary(stats) });
  return { results, stats };
}

function callSpeed(s) {
  if (!s.ms) return '';
  const secs = (s.ms / 1000).toFixed(1);
  if (!s.completionTokens) return ` · ${secs}s`;
  return ` · ${secs}s · ${(s.completionTokens / (s.ms / 1000)).toFixed(0)} tok/s` +
         ` (${s.completionTokens} out, ${s.promptTokens} in)`;
}
