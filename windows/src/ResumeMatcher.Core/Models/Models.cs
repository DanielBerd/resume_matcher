namespace ResumeMatcher.Core.Models;

/// <summary>A single job posting, read from a file in the jobs folder.</summary>
public sealed record JobPosting(string Source, string Title, string Body);

/// <summary>A resume file and the text extracted from it.</summary>
public sealed record Resume(string Path, string Text)
{
    public string Name => System.IO.Path.GetFileName(Path);
}

/// <summary>One model verdict: how well a resume fits a job.</summary>
public sealed record MatchResult(Resume Resume, JobPosting Job, int Score, string Comment);

/// <summary>Where the model runs. Both speak the OpenAI-compatible API.</summary>
public enum LlmMode { Local, Hosted }
