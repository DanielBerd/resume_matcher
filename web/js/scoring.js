// The prompt and the reply parsing. Ported verbatim in behaviour from the
// Python app on main, so a given model reply scores the same here.

export const SYSTEM_PROMPT = `You are a recruitment assistant. You will be given one job posting and one
candidate resume. Judge how well the candidate fits the job.

Reply with nothing but a JSON object in exactly this shape:
{"score": <integer 0-100>, "comment": "<one sentence>"}

The score is 0 for no fit at all and 100 for a perfect fit. The comment is a
single sentence justifying the score. Do not add any text outside the JSON.`;

export function buildUserPrompt(job, resume) {
  return `JOB POSTING
Title: ${job.title}

${job.body}

CANDIDATE RESUME
File: ${resume.name}

${resume.text}`;
}

const THINK = /<think>.*?<\/think>/gis;
const JSON_OBJECT = /\{[^{}]*"score"\s*:\s*-?\d+[^{}]*\}/s;
const FIRST_NUMBER = /-?\d+/;

const clamp = (n) => Math.max(0, Math.min(100, n));

/**
 * Pull a score and comment out of a model reply.
 *
 * Reasoning-tuned models wrap their thinking in <think> blocks and often fence
 * the JSON, so that is stripped before the object is located. With no usable
 * JSON, the first number wins — which is what a model ignoring the format
 * usually leads with.
 */
export function parseReply(reply) {
  const text = String(reply ?? '').replace(THINK, '').trim();

  const match = text.match(JSON_OBJECT);
  if (match) {
    try {
      const obj = JSON.parse(match[0]);
      if (Number.isFinite(obj.score)) {
        return { score: clamp(Math.trunc(obj.score)), comment: String(obj.comment ?? '').trim() };
      }
    } catch { /* fall through to the number fallback */ }
  }

  const num = text.match(FIRST_NUMBER);
  if (num) {
    const comment = text.replace(num[0], ' ').trim().replace(/^[\s.,:\-]+|[\s.,:\-]+$/g, '');
    return { score: clamp(parseInt(num[0], 10)), comment: comment || '(no comment returned)' };
  }

  return { score: 0, comment: "Could not read a score from the model's reply." };
}
