using System.Net;
using ResumeMatcher.Core.Models;
using ResumeMatcher.Core.Services;
using Xunit;

namespace ResumeMatcher.Tests;

public class MatcherTests
{
    private static Resume R(string name) => new(Path.Combine("/resumes", name), $"Text of {name}");

    [Fact]
    public async Task ScoresEveryPairExactlyOnce()
    {
        using var server = new FakeServer();
        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 4, TopN = 5 };
        using var client = new LlmClient(settings);

        var jobs = new[] { new JobPosting("a.txt", "A", "..."), new JobPosting("b.txt", "B", "...") };
        var resumes = Enumerable.Range(1, 5).Select(i => R($"r{i}.pdf")).ToArray();

        var results = await new Matcher(settings, client).RunAsync(jobs, resumes);

        Assert.Equal(10, server.Calls);             // 2 jobs x 5 resumes, no duplicates
        Assert.Equal(2, results.Count);
        Assert.All(results.Values, list => Assert.Equal(5, list.Count));
    }

    [Fact]
    public async Task ActuallyRunsRequestsInParallelUpToTheLimit()
    {
        using var server = new FakeServer();
        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 4, TopN = 5 };
        using var client = new LlmClient(settings);

        await new Matcher(settings, client).RunAsync(
            [new JobPosting("a.txt", "A", "...")],
            Enumerable.Range(1, 12).Select(i => R($"r{i}.pdf")).ToArray());

        Assert.Equal(12, server.Calls);
        Assert.True(server.PeakConcurrency > 1, $"expected overlap, saw {server.PeakConcurrency}");
        Assert.True(server.PeakConcurrency <= 4, $"exceeded the limit: {server.PeakConcurrency}");
    }

    [Fact]
    public async Task ConcurrencyOfOneMeansStrictlySequential()
    {
        using var server = new FakeServer();
        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 1, TopN = 5 };
        using var client = new LlmClient(settings);

        await new Matcher(settings, client).RunAsync(
            [new JobPosting("a.txt", "A", "...")],
            Enumerable.Range(1, 5).Select(i => R($"r{i}.pdf")).ToArray());

        Assert.Equal(1, server.PeakConcurrency);
    }

    [Fact]
    public async Task KeepsOnlyTheTopNSortedWithTiesBrokenByName()
    {
        using var server = new FakeServer();
        // Fixed scores by call order; two of them tie on 80.
        var scores = new[] { 40, 80, 95, 80, 10 };
        server.OnChat = n => (HttpStatusCode.OK, FakeServer.ChatReply(scores[n - 1], $"c{n}"));

        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 1, TopN = 3 };
        using var client = new LlmClient(settings);

        var results = await new Matcher(settings, client).RunAsync(
            [new JobPosting("a.txt", "A", "...")],
            [R("a.pdf"), R("b.pdf"), R("c.pdf"), R("d.pdf"), R("e.pdf")]);

        var top = results.Values.Single();
        Assert.Equal(3, top.Count);
        Assert.Equal([95, 80, 80], top.Select(t => t.Score));
        Assert.Equal("c.pdf", top[0].Resume.Name);
        // b and d both scored 80; the name decides, so runs are reproducible.
        Assert.Equal(["b.pdf", "d.pdf"], top.Skip(1).Select(t => t.Resume.Name));
    }

    [Fact]
    public async Task OneFailingResumeDoesNotSinkTheRun()
    {
        using var server = new FakeServer();
        server.OnChat = n => n == 2
            ? (HttpStatusCode.BadRequest, """{"error": {"message": "context overflow"}}""")
            : null;

        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 1, TopN = 5 };
        using var client = new LlmClient(settings);

        var messages = new List<string>();
        var results = await new Matcher(settings, client).RunAsync(
            [new JobPosting("a.txt", "A", "...")],
            [R("a.pdf"), R("b.pdf"), R("c.pdf")],
            new Progress<MatchProgress>(p => { lock (messages) messages.Add(p.Message); }));

        Assert.Equal(2, results.Values.Single().Count);        // the other two still scored
    }

    [Fact]
    public async Task ReportsProgressThatReachesTheTotal()
    {
        using var server = new FakeServer();
        var settings = new AppSettings { BaseUrl = server.BaseUrl, Concurrency = 2, TopN = 5 };
        using var client = new LlmClient(settings);

        var seen = new List<MatchProgress>();
        await new Matcher(settings, client).RunAsync(
            [new JobPosting("a.txt", "A", "...")],
            Enumerable.Range(1, 4).Select(i => R($"r{i}.pdf")).ToArray(),
            new Progress<MatchProgress>(p => { lock (seen) seen.Add(p); }));

        await Task.Delay(100);      // Progress<T> posts asynchronously
        lock (seen)
        {
            Assert.Contains(seen, p => p is { Done: 4, Total: 4 });
            Assert.Equal(1.0, seen.Max(p => p.Fraction));
        }
    }
}
