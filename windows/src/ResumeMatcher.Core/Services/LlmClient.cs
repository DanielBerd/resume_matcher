using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using ResumeMatcher.Core.Models;

namespace ResumeMatcher.Core.Services;

/// <summary>Thrown when the server can be reached but cannot serve the request.</summary>
public sealed class LlmException(string message, Exception? inner = null) : Exception(message, inner);

/// <summary>
/// Talks to any OpenAI-compatible server: Unsloth Desktop on localhost, or a
/// hosted API.
///
/// The retry policy is deliberate and mirrors the Python client: a request that
/// timed out is NEVER resent, because the server is probably still working on
/// it and a second copy doubles the load and produces a reply nobody reads.
/// Only a "busy" answer (429/503, where the request was refused outright) is
/// retried, with backoff.
/// </summary>
public sealed class LlmClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly AppSettings _settings;

    public LlmClient(AppSettings settings, HttpMessageHandler? handler = null)
    {
        _settings = settings;
        _http = handler is null ? new HttpClient() : new HttpClient(handler);
        _http.Timeout = TimeSpan.FromSeconds(settings.TimeoutSeconds);
        _http.BaseAddress = new Uri(settings.BaseUrl.TrimEnd('/') + "/");
        if (!string.IsNullOrWhiteSpace(settings.ApiKey))
            _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", settings.ApiKey);
    }

    /// <summary>Model ids the server reports. Short timeout: this is the reachability check.</summary>
    public async Task<List<string>> ListModelsAsync(CancellationToken ct = default)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(15));
        try
        {
            using var response = await _http.GetAsync("models", cts.Token).ConfigureAwait(false);
            await ThrowIfBadAsync(response).ConfigureAwait(false);
            var list = await response.Content.ReadFromJsonAsync<ModelList>(cts.Token).ConfigureAwait(false);
            return list?.Data?.Select(m => m.Id).Where(id => !string.IsNullOrEmpty(id)).ToList() ?? [];
        }
        catch (TaskCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new LlmException($"No answer from {Host} within 15 seconds.");
        }
        catch (HttpRequestException e)
        {
            throw new LlmException($"Cannot reach {Host}: {e.Message}", e);
        }
    }

    /// <summary>Score one resume against one job. Its own request, its own context —
    /// resumes are never mixed together.</summary>
    public async Task<MatchResult> ScoreAsync(JobPosting job, Resume resume, CancellationToken ct = default)
    {
        var reply = await CompleteAsync(Scoring.SystemPrompt, Scoring.BuildUserPrompt(job, resume), ct)
            .ConfigureAwait(false);
        var (score, comment) = Scoring.Parse(reply);
        return new MatchResult(resume, job, score, comment);
    }

    /// <summary>One chat completion, with the retry policy described on the class.</summary>
    public async Task<string> CompleteAsync(string systemPrompt, string userPrompt, CancellationToken ct = default)
    {
        var request = new ChatRequest
        {
            Model = _settings.Model,
            Temperature = _settings.Temperature,
            MaxTokens = _settings.MaxTokens,
            Messages =
            [
                new ChatMessage { Role = "system", Content = systemPrompt },
                new ChatMessage { Role = "user", Content = userPrompt },
            ],
        };

        var response = await SendWithRetryAsync(request, ct).ConfigureAwait(false);
        var choice = response.Choices?.FirstOrDefault()
            ?? throw new LlmException("The server returned no choices.");

        // Some chat templates put the answer in a reasoning field instead of content.
        var content = choice.Message?.Content;
        if (string.IsNullOrWhiteSpace(content)) content = choice.Message?.ReasoningContent;

        if (string.IsNullOrWhiteSpace(content))
            throw new LlmException(
                $"The model returned an empty reply (finish_reason={choice.FinishReason}). " +
                "If that is 'length', it spent its whole budget on reasoning before answering — raise Max tokens.");

        return content;
    }

    private async Task<ChatResponse> SendWithRetryAsync(ChatRequest request, CancellationToken ct)
    {
        var delay = TimeSpan.FromSeconds(1);
        var waited = TimeSpan.Zero;
        var reconnects = 0;

        while (true)
        {
            try
            {
                // Buffered rather than PostAsJsonAsync: that serializes lazily, so the
                // request goes out chunked with no Content-Length, which some
                // OpenAI-compatible servers and API gateways reject.
                using var content = new StringContent(
                    JsonSerializer.Serialize(request), Encoding.UTF8, "application/json");
                using var response = await _http.PostAsync("chat/completions", content, ct).ConfigureAwait(false);

                if (response.StatusCode is HttpStatusCode.TooManyRequests or HttpStatusCode.ServiceUnavailable)
                {
                    // The server refused the request outright, so resending is safe.
                    if (waited >= TimeSpan.FromSeconds(_settings.BusyWaitSeconds))
                        throw new LlmException(
                            $"{Host} stayed busy for {_settings.BusyWaitSeconds}s. Lower the concurrency, " +
                            "or raise the server's parallel slots.");
                }
                else
                {
                    await ThrowIfBadAsync(response).ConfigureAwait(false);
                    return await response.Content.ReadFromJsonAsync<ChatResponse>(ct).ConfigureAwait(false)
                        ?? throw new LlmException("The server returned an empty body.");
                }
            }
            catch (TaskCanceledException) when (!ct.IsCancellationRequested)
            {
                // Timed out. Never resend: the server is probably still working on it.
                throw new LlmException(
                    $"The request timed out after {_settings.TimeoutSeconds}s. With {_settings.Concurrency} " +
                    "in flight the server may be queueing them — lower the concurrency or raise its slots. " +
                    "(Not resent: the server would still finish the original.)");
            }
            catch (HttpRequestException e)
            {
                // Nothing reached the server, so one retry cannot duplicate work.
                if (reconnects++ >= 1) throw new LlmException($"Cannot reach {Host}: {e.Message}", e);
            }

            await Task.Delay(delay, ct).ConfigureAwait(false);
            waited += delay;
            delay = TimeSpan.FromSeconds(Math.Min(delay.TotalSeconds * 2, 10));
        }
    }

    /// <summary>Turn an error status into a message that says what to do about it.</summary>
    private static async Task ThrowIfBadAsync(HttpResponseMessage response)
    {
        if (response.IsSuccessStatusCode) return;

        var body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
        var detail = Summarise(body);

        throw new LlmException(response.StatusCode switch
        {
            HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden =>
                $"The server rejected the API key ({(int)response.StatusCode}). Check it on the Server tab.",
            HttpStatusCode.NotFound =>
                $"Not found ({(int)response.StatusCode}). Check the base URL, and that the model name matches " +
                $"one the server offers. {detail}",
            HttpStatusCode.BadRequest when detail.Contains("no model loaded", StringComparison.OrdinalIgnoreCase) =>
                "The server has no model loaded. In Unsloth Desktop either load the model, or turn on " +
                "Settings > API > \"Switch model by request\" so it loads them on demand.",
            _ => $"The server answered {(int)response.StatusCode}. {detail}",
        });
    }

    /// <summary>Lift the human-readable part out of an error body.</summary>
    private static string Summarise(string body)
    {
        if (string.IsNullOrWhiteSpace(body)) return "";
        try
        {
            using var doc = JsonDocument.Parse(body);
            if (doc.RootElement.TryGetProperty("error", out var error))
            {
                if (error.ValueKind == JsonValueKind.String) return error.GetString() ?? "";
                if (error.TryGetProperty("message", out var message)) return message.GetString() ?? "";
            }
        }
        catch (JsonException) { /* not JSON; fall through to the raw text */ }

        return body.Length > 300 ? body[..300] + "..." : body;
    }

    public string Host
    {
        get
        {
            try { return new Uri(_settings.BaseUrl).Host; }
            catch (UriFormatException) { return _settings.BaseUrl; }
        }
    }

    public void Dispose() => _http.Dispose();

    // ---------- wire types ----------

    private sealed class ChatRequest
    {
        [JsonPropertyName("model")] public string Model { get; set; } = "";
        [JsonPropertyName("messages")] public List<ChatMessage> Messages { get; set; } = [];
        [JsonPropertyName("temperature")] public double Temperature { get; set; }
        [JsonPropertyName("max_tokens")] public int MaxTokens { get; set; }
    }

    private sealed class ChatMessage
    {
        [JsonPropertyName("role")] public string Role { get; set; } = "";
        [JsonPropertyName("content")] public string Content { get; set; } = "";
    }

    private sealed class ChatResponse
    {
        [JsonPropertyName("choices")] public List<Choice>? Choices { get; set; }
    }

    private sealed class Choice
    {
        [JsonPropertyName("message")] public ReplyMessage? Message { get; set; }
        [JsonPropertyName("finish_reason")] public string? FinishReason { get; set; }
    }

    private sealed class ReplyMessage
    {
        [JsonPropertyName("content")] public string? Content { get; set; }
        [JsonPropertyName("reasoning_content")] public string? ReasoningContent { get; set; }
    }

    private sealed class ModelList
    {
        [JsonPropertyName("data")] public List<ModelEntry>? Data { get; set; }
    }

    private sealed class ModelEntry
    {
        [JsonPropertyName("id")] public string Id { get; set; } = "";
    }
}
