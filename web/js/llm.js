// Client for an OpenAI-compatible server (vLLM, Unsloth Desktop, a hosted API).
//
// The retry policy matches the desktop versions and is deliberate: a request
// that TIMED OUT is never resent, because the server is probably still working
// on it and a second copy doubles the load for a reply nobody reads. Only a
// "busy" answer (429/503), where the request was refused outright, is retried.

import { SYSTEM_PROMPT, buildUserPrompt, parseReply } from './scoring.js';

export class LlmError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class LlmClient {
  constructor(settings) {
    this.settings = settings;
    // A relative base ("/v1") keeps everything same-origin behind a reverse
    // proxy, which is the recommended setup — no CORS involved at all.
    this.base = settings.baseUrl.replace(/\/+$/, '');
  }

  get host() {
    try { return new URL(this.base, location.href).host; }
    catch { return this.base; }
  }

  #headers() {
    const h = { 'Content-Type': 'application/json' };
    if (this.settings.apiKey) h.Authorization = `Bearer ${this.settings.apiKey}`;
    return h;
  }

  /** Model ids the server reports. Doubles as the reachability check. */
  async listModels(signal) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15000);
    signal?.addEventListener('abort', () => ctrl.abort(), { once: true });
    try {
      const r = await fetch(`${this.base}/models`, { headers: this.#headers(), signal: ctrl.signal });
      await throwIfBad(r, this.host);
      const body = await r.json();
      return (body.data ?? []).map((m) => m.id).filter(Boolean);
    } catch (e) {
      if (e instanceof LlmError) throw e;
      if (e.name === 'AbortError' && !signal?.aborted) throw new LlmError(`No answer from ${this.host} within 15s.`);
      if (e.name === 'AbortError') throw e;
      throw new LlmError(cannotReach(this.host, e));
    } finally {
      clearTimeout(timer);
    }
  }

  /** Score one resume against one job: its own request, its own context. */
  async score(job, resume, signal) {
    const { content, usage, ms } = await this.#complete(
      SYSTEM_PROMPT, buildUserPrompt(job, resume), signal);
    const { score, comment } = parseReply(content);
    return { resume, job, score, comment, stats: { ...usage, ms } };
  }

  async #complete(system, user, signal) {
    const payload = {
      model: this.settings.model,
      messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
      temperature: this.settings.temperature,
      max_tokens: this.settings.maxTokens,
    };

    const started = performance.now();
    const data = await this.#send(payload, signal);
    const ms = performance.now() - started;

    const choice = data.choices?.[0];
    if (!choice) throw new LlmError('The server returned no choices.');

    // Some chat templates put the answer in a reasoning field, not content.
    const content = choice.message?.content?.trim() || choice.message?.reasoning_content?.trim();
    if (!content) {
      throw new LlmError(
        `The model returned an empty reply (finish_reason=${choice.finish_reason}). ` +
        "If that is 'length', it spent its whole budget on reasoning before answering — raise Max tokens.");
    }

    // usage is optional in the OpenAI schema; vLLM and llama.cpp both send it.
    const u = data.usage ?? {};
    return {
      content,
      ms,
      usage: {
        promptTokens: Number(u.prompt_tokens) || 0,
        completionTokens: Number(u.completion_tokens) || 0,
      },
    };
  }

  async #send(payload, signal) {
    let delay = 1000, waited = 0, reconnects = 0;

    for (;;) {
      signal?.throwIfAborted();

      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')),
                               this.settings.timeoutSeconds * 1000);
      const onAbort = () => ctrl.abort(signal.reason);
      signal?.addEventListener('abort', onAbort, { once: true });

      let response;
      try {
        response = await fetch(`${this.base}/chat/completions`, {
          method: 'POST',
          headers: this.#headers(),
          body: JSON.stringify(payload),
          signal: ctrl.signal,
        });
      } catch (e) {
        if (signal?.aborted) throw signal.reason ?? e;

        if (ctrl.signal.reason?.name === 'TimeoutError') {
          // Never resent: the server is probably still working on the original.
          throw new LlmError(
            `The request timed out after ${this.settings.timeoutSeconds}s. With ` +
            `${this.settings.concurrency} in flight the server may be queueing them — lower the ` +
            'concurrency or give the server more capacity. (Not resent: the server would still ' +
            'finish the original.)');
        }
        // Nothing reached the server, so one retry cannot duplicate work.
        if (reconnects++ >= 1) throw new LlmError(cannotReach(this.host, e));
        await sleep(delay); waited += delay; delay = Math.min(delay * 2, 10000);
        continue;
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);
      }

      if (response.status === 429 || response.status === 503) {
        if (waited >= this.settings.busyWaitSeconds * 1000) {
          throw new LlmError(
            `${this.host} stayed busy for ${this.settings.busyWaitSeconds}s. Lower the concurrency, ` +
            'or give the server more capacity.');
        }
        await sleep(delay); waited += delay; delay = Math.min(delay * 2, 10000);
        continue;
      }

      await throwIfBad(response, this.host);
      return response.json();
    }
  }
}

function cannotReach(host, e) {
  return `Cannot reach ${host}: ${e.message}. If the model server is on another ` +
         'origin, the browser blocks it unless that server sends CORS headers — ' +
         'see the README on putting both behind one reverse proxy.';
}

/** Turn an error status into a message that says what to do about it. */
async function throwIfBad(response, host) {
  if (response.ok) return;
  const detail = summarise(await response.text().catch(() => ''));

  if (response.status === 401 || response.status === 403) {
    throw new LlmError(`The server rejected the API key (${response.status}). Check it on the Server tab.`);
  }
  if (response.status === 404) {
    throw new LlmError(
      `Not found (404). Check the base URL, and that the model name matches one the server offers. ${detail}`);
  }
  if (response.status === 400 && /no model loaded/i.test(detail)) {
    throw new LlmError('The server has no model loaded.');
  }
  throw new LlmError(`${host} answered ${response.status}. ${detail}`);
}

function summarise(body) {
  if (!body) return '';
  try {
    const j = JSON.parse(body);
    const err = j.error;
    if (typeof err === 'string') return err;
    if (err?.message) return err.message;
  } catch { /* not JSON */ }
  return body.length > 300 ? body.slice(0, 300) + '…' : body;
}
