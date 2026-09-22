using System.Net;
using System.Text.Json;
using ResumeMatcher.Core.Models;
using ResumeMatcher.Core.Services;
using Xunit;

namespace ResumeMatcher.Tests;

public class LlmClientTests
{
    private static AppSettings SettingsFor(FakeServer server, Action<AppSettings>? tweak = null)
    {
        var s = new AppSettings { BaseUrl = server.BaseUrl, ApiKey = "test-key", Model = "gemma-4-12b", TopN = 5 };
        tweak?.Invoke(s);
        return s;
    }

    private static readonly JobPosting Job = new("job.txt", "Senior Python Engineer", "Python, Azure, 5 years.");
    private static Resume ResumeNamed(string name) => new(Path.Combine("/resumes", name), "Python engineer, 6 years.");

    [Fact]
    public async Task ListsModelsAndScoresAResume()
    {
        using var server = new FakeServer();
        using var client = new LlmClient(SettingsFor(server));

        Assert.Equal(["gemma-4-12b-it-qat", "gemma-4-e4b-it-qat"], await client.ListModelsAsync());

        var result = await client.ScoreAsync(Job, ResumeNamed("anna.pdf"));
        Assert.InRange(result.Score, 0, 100);
        Assert.Equal("anna.pdf", result.Resume.Name);
    }

    [Fact]
    public async Task SendsExactlyOneJobAndOneResumePerRequest()
    {
        using var server = new FakeServer();
        using var client = new LlmClient(SettingsFor(server));

        await client.ScoreAsync(Job, ResumeNamed("anna.pdf"));
        await client.ScoreAsync(Job, ResumeNamed("marcus.pdf"));

        Assert.Equal(2, server.Calls);
        foreach (var body in server.Bodies)
        {
            using var doc = JsonDocument.Parse(body);
            var messages = doc.RootElement.GetProperty("messages");
            Assert.Equal(2, messages.GetArrayLength());     // system + user, no history
        }
        // Neither request mentions the other resume: contexts are never mixed.
        Assert.DoesNotContain("marcus.pdf", server.Bodies[0]);
        Assert.DoesNotContain("anna.pdf", server.Bodies[1]);
    }

    [Fact]
    public async Task RetriesABusyAnswerThenSucceeds()
    {
        using var server = new FakeServer();
        // Refuse the first two outright, then answer.
        server.OnChat = n => n <= 2
            ? (HttpStatusCode.TooManyRequests, """{"error": {"message": "busy"}}""")
            : null;

        using var client = new LlmClient(SettingsFor(server, s => s.BusyWaitSeconds = 30));
        var result = await client.ScoreAsync(Job, ResumeNamed("anna.pdf"));

        Assert.Equal(3, server.Calls);              // two refusals plus the real one
        Assert.InRange(result.Score, 0, 100);
    }

    [Fact]
    public async Task NeverResendsARequestThatTimedOut()
    {
        using var server = new FakeServer();
        // Accept the request and then stall well past the client's timeout.
        server.OnChat = _ => { Thread.Sleep(2500); return (HttpStatusCode.OK, FakeServer.ChatReply(50, "late")); };

        using var client = new LlmClient(SettingsFor(server, s => s.TimeoutSeconds = 1));

        var error = await Assert.ThrowsAsync<LlmException>(() => client.ScoreAsync(Job, ResumeNamed("anna.pdf")));
        Assert.Contains("timed out", error.Message, StringComparison.OrdinalIgnoreCase);

        // The server must have seen the request exactly once: a resend would
        // double the work while the original is still being processed.
        await Task.Delay(3000);
        Assert.Equal(1, server.Calls);
    }

    [Fact]
    public async Task ExplainsAnUnloadedModelRatherThanShowingRawJson()
    {
        using var server = new FakeServer();
        server.OnChat = _ => (HttpStatusCode.BadRequest, """{"error": {"message": "No model loaded"}}""");

        using var client = new LlmClient(SettingsFor(server));
        var error = await Assert.ThrowsAsync<LlmException>(() => client.ScoreAsync(Job, ResumeNamed("a.pdf")));

        Assert.Contains("Switch model by request", error.Message);
    }

    [Fact]
    public async Task ExplainsARejectedKey()
    {
        using var server = new FakeServer();
        server.OnChat = _ => (HttpStatusCode.Unauthorized, """{"error": {"message": "bad key"}}""");

        using var client = new LlmClient(SettingsFor(server));
        var error = await Assert.ThrowsAsync<LlmException>(() => client.ScoreAsync(Job, ResumeNamed("a.pdf")));

        Assert.Contains("API key", error.Message);
        Assert.Contains("Server tab", error.Message);
    }

    [Fact]
    public async Task FallsBackToTheReasoningFieldWhenContentIsEmpty()
    {
        using var server = new FakeServer();
        server.OnChat = _ => (HttpStatusCode.OK, JsonSerializer.Serialize(new
        {
            choices = new[]
            {
                new
                {
                    finish_reason = "stop",
                    message = new { role = "assistant", content = "", reasoning_content = """{"score": 64, "comment": "Reasoned."}""" },
                },
            },
        }));

        using var client = new LlmClient(SettingsFor(server));
        Assert.Equal(64, (await client.ScoreAsync(Job, ResumeNamed("a.pdf"))).Score);
    }

    [Fact]
    public async Task SaysWhatToDoWhenTheReplyIsCompletelyEmpty()
    {
        using var server = new FakeServer();
        server.OnChat = _ => (HttpStatusCode.OK, JsonSerializer.Serialize(new
        {
            choices = new[] { new { finish_reason = "length", message = new { role = "assistant", content = "" } } },
        }));

        using var client = new LlmClient(SettingsFor(server));
        var error = await Assert.ThrowsAsync<LlmException>(() => client.ScoreAsync(Job, ResumeNamed("a.pdf")));

        Assert.Contains("Max tokens", error.Message);
    }
}
