using ResumeMatcher.Core.Models;
using ResumeMatcher.Core.Services;
using Xunit;

namespace ResumeMatcher.Tests;

public class SettingsTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("rm-settings").FullName;
    public void Dispose() => Directory.Delete(_dir, recursive: true);

    [Fact]
    public void RoundTripsThroughDisk()
    {
        var path = Path.Combine(_dir, "settings.json");
        new AppSettings { Mode = LlmMode.Hosted, BaseUrl = "https://api.openai.com/v1", Model = "gpt-4o-mini", Concurrency = 8 }
            .Save(path);

        var loaded = AppSettings.Load(path);

        Assert.Equal(LlmMode.Hosted, loaded.Mode);
        Assert.True(loaded.IsHosted);
        Assert.Equal("gpt-4o-mini", loaded.Model);
        Assert.Equal(8, loaded.Concurrency);
    }

    [Fact]
    public void FallsBackToDefaultsWhenTheFileIsMissingOrCorrupt()
    {
        Assert.Equal("gemma-4-12b", AppSettings.Load(Path.Combine(_dir, "absent.json")).Model);

        var bad = Path.Combine(_dir, "bad.json");
        File.WriteAllText(bad, "{ not json at all");
        Assert.Equal(LlmMode.Local, AppSettings.Load(bad).Mode);
    }

    [Fact]
    public void CloneIsIndependentOfTheOriginal()
    {
        var original = new AppSettings { Model = "a", Concurrency = 2 };
        var copy = original.Clone();
        copy.Model = "b";
        copy.Concurrency = 9;

        Assert.Equal("a", original.Model);
        Assert.Equal(2, original.Concurrency);
    }

    [Fact]
    public void WorkingFoldersDefaultUnderDocumentsButCanBeOverridden()
    {
        Assert.Contains("Resume Matcher", new AppSettings().Resumes);
        Assert.Equal("/custom/cv", new AppSettings { ResumesDir = "/custom/cv" }.Resumes);
    }
}

public class ProviderTests
{
    [Fact]
    public void MatchesAServerIdBySubstringIgnoringPrefixAndSuffix() =>
        Assert.Equal("unsloth/gemma-4-12B-it-qat-GGUF",
            Provider.PickDefaultModel(
                ["unsloth/gemma-4-E4B-it-qat-GGUF", "unsloth/gemma-4-12B-it-qat-GGUF"], "gemma-4-12b"));

    [Fact]
    public void FallsBackToTheFirstModelWhenNothingMatches() =>
        Assert.Equal("llama-3.3-70b", Provider.PickDefaultModel(["llama-3.3-70b", "mistral"], "gemma"));

    [Fact]
    public void KeepsThePreferenceWhenTheServerListsNothing() =>
        Assert.Equal("gemma-4-12b", Provider.PickDefaultModel([], "gemma-4-12b"));

    [Theory]
    [InlineData("Unsloth Desktop", LlmMode.Local, false)]
    [InlineData("OpenAI", LlmMode.Hosted, true)]
    [InlineData("Azure AI Foundry", LlmMode.Hosted, true)]
    public void PresetsCarryTheRightModeAndKeyRequirement(string name, LlmMode mode, bool needsKey)
    {
        var provider = Provider.Find(name);
        Assert.NotNull(provider);
        Assert.Equal(mode, provider!.Mode);
        Assert.Equal(needsKey, provider.NeedsKey);
    }

    [Fact]
    public void AzurePresetUsesTheOpenAiCompatibleV1Path() =>
        // The classic ?api-version= endpoint needs a different auth header, so the
        // preset must point at the v1 surface this client can actually talk to.
        Assert.EndsWith("/openai/v1", Provider.Find("Azure AI Foundry")!.BaseUrl);
}

public class ReportWriterTests
{
    private static Resume R(string name) => new(Path.Combine(Path.GetTempPath(), name), "text");

    private static Dictionary<JobPosting, List<MatchResult>> Sample()
    {
        var job = new JobPosting("job.txt", "Senior Python Engineer", "body");
        return new Dictionary<JobPosting, List<MatchResult>>
        {
            [job] =
            [
                new(R("anna.pdf"), job, 91, "Excellent match."),
                new(R("marcus.pdf"), job, 64, "Some overlap."),
                new(R("emma.pdf"), job, 12, "Wrong field."),
            ],
        };
    }

    [Fact]
    public void ShowsEveryMatchWithItsScoreBand()
    {
        var html = ReportWriter.BuildHtml(Sample(), "2026-09-22_10-00-00");

        Assert.Contains("Senior Python Engineer", html);
        Assert.Contains("badge good\">91", html);
        Assert.Contains("badge mid\">64", html);
        Assert.Contains("badge low\">12", html);
        Assert.Contains("prefers-color-scheme: dark", html);    // follows the Windows theme
    }

    [Fact]
    public void EscapesTextSoAResumeNameCannotBreakThePage()
    {
        var job = new JobPosting("j.txt", "Dev <script>alert(1)</script>", "b");
        var data = new Dictionary<JobPosting, List<MatchResult>>
        {
            [job] = [new(R("a.pdf"), job, 50, "Comment with <b>tags</b> & an ampersand")],
        };

        var html = ReportWriter.BuildHtml(data, "stamp");

        Assert.DoesNotContain("<script>alert(1)</script>", html);
        Assert.Contains("&lt;script&gt;", html);
        Assert.Contains("&amp;", html);
    }

    [Fact]
    public void LinksEachResumeToTheFileOnDisk() =>
        Assert.Contains("file:///", ReportWriter.BuildHtml(Sample(), "stamp"));

    [Fact]
    public void SaysSoWhenAJobHadNoUsableResumes()
    {
        var job = new JobPosting("j.txt", "Empty", "b");
        var html = ReportWriter.BuildHtml(new() { [job] = [] }, "stamp");
        Assert.Contains("No resumes could be scored", html);
    }
}
