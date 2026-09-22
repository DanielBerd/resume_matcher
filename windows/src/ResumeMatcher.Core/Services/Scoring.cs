using System.Text.Json;
using System.Text.RegularExpressions;
using ResumeMatcher.Core.Models;

namespace ResumeMatcher.Core.Services;

/// <summary>The prompt that asks for a score, and the parsing of what comes back.</summary>
public static partial class Scoring
{
    public const string SystemPrompt = """
        You are a recruitment assistant. You will be given one job posting and one
        candidate resume. Judge how well the candidate fits the job.

        Reply with nothing but a JSON object in exactly this shape:
        {"score": <integer 0-100>, "comment": "<one sentence>"}

        The score is 0 for no fit at all and 100 for a perfect fit. The comment is a
        single sentence justifying the score. Do not add any text outside the JSON.
        """;

    public static string BuildUserPrompt(JobPosting job, Resume resume) => $"""
        JOB POSTING
        Title: {job.Title}

        {job.Body}

        CANDIDATE RESUME
        File: {resume.Name}

        {resume.Text}
        """;

    [GeneratedRegex(@"<think>.*?</think>", RegexOptions.Singleline | RegexOptions.IgnoreCase)]
    private static partial Regex ThinkBlock();

    [GeneratedRegex(@"\{[^{}]*""score""\s*:\s*-?\d+[^{}]*\}", RegexOptions.Singleline)]
    private static partial Regex JsonObject();

    [GeneratedRegex(@"-?\d+")]
    private static partial Regex FirstNumber();

    /// <summary>
    /// Pull a score and comment out of a model reply.
    ///
    /// Reasoning-tuned models wrap their thinking in &lt;think&gt; blocks and
    /// often fence the JSON, so the text is stripped before the JSON object is
    /// located. When there is no usable JSON, the first number in the reply is
    /// used, which is what a model that ignores the format usually leads with.
    /// </summary>
    public static (int Score, string Comment) Parse(string reply)
    {
        var text = ThinkBlock().Replace(reply ?? "", "").Trim();

        var match = JsonObject().Match(text);
        if (match.Success)
        {
            try
            {
                using var doc = JsonDocument.Parse(match.Value);
                var root = doc.RootElement;
                var score = root.TryGetProperty("score", out var s) && s.TryGetInt32(out var i) ? i : 0;
                var comment = root.TryGetProperty("comment", out var c) ? c.GetString() ?? "" : "";
                return (Clamp(score), comment.Trim());
            }
            catch (JsonException)
            {
                // fall through to the number fallback
            }
        }

        var number = FirstNumber().Match(text);
        if (number.Success && int.TryParse(number.Value, out var parsed))
        {
            var comment = text.Replace(number.Value, " ").Trim(' ', '.', ',', ':', '-', '\n', '\r');
            return (Clamp(parsed), comment.Length > 0 ? comment : "(no comment returned)");
        }

        return (0, "Could not read a score from the model's reply.");
    }

    private static int Clamp(int score) => Math.Max(0, Math.Min(100, score));
}
