// Scores every resume against every job and keeps the best per job.

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
  const total = jobs.length * resumes.length;
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
          done += 1;
          onProgress?.({ done, total, message: `[${done}/${total}] ${resume.name} scored ${result.score}` });
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

  onProgress?.({ done: total, total, message: 'Done' });
  return results;
}
