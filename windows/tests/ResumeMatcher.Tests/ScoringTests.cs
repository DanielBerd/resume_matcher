using ResumeMatcher.Core.Services;
using Xunit;

namespace ResumeMatcher.Tests;

public class ScoringTests
{
    [Fact]
    public void ReadsPlainJson()
    {
        var (score, comment) = Scoring.Parse("""{"score": 82, "comment": "Strong Python background."}""");
        Assert.Equal(82, score);
        Assert.Equal("Strong Python background.", comment);
    }

    [Fact]
    public void IgnoresProseAndCodeFencesAroundTheJson()
    {
        var (score, _) = Scoring.Parse("""
            Sure! Here is my assessment:
            ```json
            {"score": 47, "comment": "Partial overlap only."}
            ```
            """);
        Assert.Equal(47, score);
    }

    [Fact]
    public void StripsReasoningBlocksBeforeParsing()
    {
        // The think block holds a decoy number that must not win.
        var (score, comment) = Scoring.Parse("""
            <think>Maybe 90? No, the cloud experience is missing, so lower. Say 35.</think>
            {"score": 35, "comment": "No cloud experience."}
            """);
        Assert.Equal(35, score);
        Assert.Equal("No cloud experience.", comment);
    }

    [Fact]
    public void FallsBackToTheFirstNumberWhenTheModelIgnoresTheFormat()
    {
        var (score, comment) = Scoring.Parse("I would rate this candidate 73 out of 100 for this role.");
        Assert.Equal(73, score);
        Assert.Contains("rate this candidate", comment);
    }

    [Theory]
    [InlineData("""{"score": 150, "comment": "x"}""", 100)]
    [InlineData("""{"score": -20, "comment": "x"}""", 0)]
    public void ClampsOutOfRangeScores(string reply, int expected) =>
        Assert.Equal(expected, Scoring.Parse(reply).Score);

    [Fact]
    public void ReportsFailureRatherThanGuessingWhenThereIsNoNumber()
    {
        var (score, comment) = Scoring.Parse("I cannot assess this resume.");
        Assert.Equal(0, score);
        Assert.Contains("Could not read a score", comment);
    }
}
