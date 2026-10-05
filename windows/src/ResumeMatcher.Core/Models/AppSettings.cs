using System.Text.Json;
using System.Text.Json.Serialization;

namespace ResumeMatcher.Core.Models;

/// <summary>
/// Everything a run needs, persisted as JSON.
///
/// Unlike the Python version, an installed Windows app cannot write next to
/// itself, so the settings and the working folders live under the user's
/// profile: %APPDATA%\ResumeMatcher\settings.json and
/// %USERPROFILE%\Documents\Resume Matcher\{resumes,jobs,results}.
/// </summary>
public sealed class AppSettings
{
    public LlmMode Mode { get; set; } = LlmMode.Local;
    public string Provider { get; set; } = "Unsloth Desktop";
    public string BaseUrl { get; set; } = "http://localhost:8888/v1";
    public string ApiKey { get; set; } = "local";
    public string Model { get; set; } = "gemma-4-12b";
    public int Concurrency { get; set; } = 4;
    public int TopN { get; set; } = 5;
    public double Temperature { get; set; } = 0.1;
    public int MaxTokens { get; set; } = 2048;

    /// <summary>Per-request timeout. Generous: with more requests in flight than the
    /// server has slots, a request waits in its queue before it even starts.</summary>
    public int TimeoutSeconds { get; set; } = 600;

    /// <summary>How long to keep retrying a "busy" answer (429/503) before giving up.</summary>
    public int BusyWaitSeconds { get; set; } = 120;

    public string? ResumesDir { get; set; }
    public string? JobsDir { get; set; }
    public string? ResultsDir { get; set; }

    [JsonIgnore]
    public bool IsHosted => Mode == LlmMode.Hosted;

    // ---------- locations ----------

    public static string AppDataDir =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "ResumeMatcher");

    public static string SettingsPath => Path.Combine(AppDataDir, "settings.json");

    /// <summary>Documents\Resume Matcher — visible, backed up, and writable when
    /// the program itself lives in Program Files.</summary>
    public static string DefaultRoot =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Resume Matcher");

    public string Resumes => ResumesDir ?? Path.Combine(DefaultRoot, "resumes");
    public string Jobs => JobsDir ?? Path.Combine(DefaultRoot, "jobs");
    public string Results => ResultsDir ?? Path.Combine(DefaultRoot, "results");

    /// <summary>Create the working folders if they are not there yet.</summary>
    public void EnsureFolders()
    {
        foreach (var dir in new[] { Resumes, Jobs, Results })
            Directory.CreateDirectory(dir);
    }

    // ---------- persistence ----------

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
    };

    /// <summary>Read the saved settings; defaults when the file is missing or unreadable.</summary>
    public static AppSettings Load(string? path = null)
    {
        path ??= SettingsPath;
        try
        {
            return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions) ?? new AppSettings();
        }
        catch (Exception e) when (e is IOException or JsonException or UnauthorizedAccessException)
        {
            return new AppSettings();
        }
    }

    public void Save(string? path = null)
    {
        path ??= SettingsPath;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, JsonSerializer.Serialize(this, JsonOptions));
    }

    public AppSettings Clone() =>
        JsonSerializer.Deserialize<AppSettings>(JsonSerializer.Serialize(this, JsonOptions), JsonOptions)!;
}
