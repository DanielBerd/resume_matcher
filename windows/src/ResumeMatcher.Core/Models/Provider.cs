namespace ResumeMatcher.Core.Models;

/// <summary>A one-click preset for the Server tab. Every entry speaks the
/// OpenAI-compatible API, so switching is only base URL, key and model.</summary>
public sealed record Provider(string Name, LlmMode Mode, string BaseUrl, string Model, bool NeedsKey)
{
    public static readonly IReadOnlyList<Provider> All =
    [
        new("Unsloth Desktop",              LlmMode.Local,  "http://localhost:8888/v1",        "gemma-4-12b",               false),
        new("Local (other OpenAI-compatible)", LlmMode.Local, "http://localhost:8000/v1",       "",                          false),
        new("Azure AI Foundry",             LlmMode.Hosted, "https://RESOURCE.openai.azure.com/openai/v1", "your-deployment-name", true),
        new("OpenAI",                       LlmMode.Hosted, "https://api.openai.com/v1",       "gpt-4o-mini",               true),
        new("OpenRouter",                   LlmMode.Hosted, "https://openrouter.ai/api/v1",    "google/gemma-3-27b-it",     true),
        new("Groq",                         LlmMode.Hosted, "https://api.groq.com/openai/v1",  "llama-3.3-70b-versatile",   true),
        new("Custom (OpenAI-compatible)",   LlmMode.Hosted, "",                                "",                          true),
    ];

    public static Provider? Find(string name) =>
        All.FirstOrDefault(p => string.Equals(p.Name, name, StringComparison.OrdinalIgnoreCase));

    /// <summary>Preselect the model whose id contains the preferred name, else the
    /// first. Server ids carry org prefixes and quantization suffixes we do not
    /// want to hardcode ("gemma-4-12b" matches "unsloth/gemma-4-12B-it-qat-GGUF").</summary>
    public static string PickDefaultModel(IReadOnlyList<string> models, string preferred)
    {
        if (models.Count == 0) return preferred;
        if (!string.IsNullOrWhiteSpace(preferred))
        {
            var hit = models.FirstOrDefault(m => m.Contains(preferred, StringComparison.OrdinalIgnoreCase));
            if (hit is not null) return hit;
        }
        return models[0];
    }
}
