using System.IO.Compression;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using ResumeMatcher.Core.Models;
using UglyToad.PdfPig;

namespace ResumeMatcher.Core.Services;

/// <summary>
/// Turns resume and job-posting files into plain text.
///
/// PDF goes through PdfPig (managed, no native dependency and no Tesseract
/// install). DOCX is a zip holding word/document.xml, so it is read with the
/// framework's own zip and XML support rather than a library.
/// </summary>
public static class DocumentReader
{
    public static readonly string[] ResumeExtensions = [".pdf", ".docx", ".txt", ".md"];
    public static readonly string[] JobExtensions = [".txt", ".md", ".eml", ".pdf", ".docx"];

    /// <summary>Read every supported resume in a folder, skipping ones with no text.</summary>
    public static List<Resume> LoadResumes(string dir)
    {
        var resumes = new List<Resume>();
        if (!Directory.Exists(dir)) return resumes;

        foreach (var path in Directory.EnumerateFiles(dir).OrderBy(p => p, StringComparer.OrdinalIgnoreCase))
        {
            if (!ResumeExtensions.Contains(Path.GetExtension(path).ToLowerInvariant())) continue;
            var text = TryExtract(path);
            if (!string.IsNullOrWhiteSpace(text)) resumes.Add(new Resume(path, text));
        }
        return resumes;
    }

    public static List<JobPosting> LoadJobs(string dir)
    {
        var jobs = new List<JobPosting>();
        if (!Directory.Exists(dir)) return jobs;

        foreach (var path in Directory.EnumerateFiles(dir).OrderBy(p => p, StringComparer.OrdinalIgnoreCase))
        {
            if (!JobExtensions.Contains(Path.GetExtension(path).ToLowerInvariant())) continue;
            var job = TryLoadJob(path);
            if (job is not null) jobs.Add(job);
        }
        return jobs;
    }

    /// <summary>Read one posting. .eml keeps its Subject as the title.</summary>
    public static JobPosting? TryLoadJob(string path)
    {
        try
        {
            if (Path.GetExtension(path).Equals(".eml", StringComparison.OrdinalIgnoreCase))
                return ParseEml(path);

            var text = TryExtract(path);
            if (string.IsNullOrWhiteSpace(text)) return null;

            // First non-empty line doubles as the title.
            var title = text.Split('\n', StringSplitOptions.RemoveEmptyEntries)
                            .FirstOrDefault(l => l.Trim().Length > 0)?.Trim()
                        ?? Path.GetFileNameWithoutExtension(path);
            return new JobPosting(Path.GetFileName(path), title, text);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public static string TryExtract(string path)
    {
        try
        {
            return Path.GetExtension(path).ToLowerInvariant() switch
            {
                ".pdf" => ExtractPdf(path),
                ".docx" => ExtractDocx(path),
                ".eml" => ParseEml(path).Body,
                _ => File.ReadAllText(path),
            };
        }
        catch (Exception)
        {
            // A single unreadable file must not stop a run; the caller skips empties.
            return "";
        }
    }

    /// <summary>
    /// PDF text runs carry no explicit spaces, so page.Text glues words together
    /// ("Anna KovacsSenior Engineer"). Grouping into words and laying them back
    /// out by their position keeps the text readable, which matters because it
    /// is what the model is asked to judge.
    /// </summary>
    private static string ExtractPdf(string path)
    {
        using var doc = PdfDocument.Open(path);
        var sb = new StringBuilder();

        foreach (var page in doc.GetPages())
        {
            var words = page.GetWords().ToList();
            if (words.Count == 0)
            {
                sb.AppendLine(page.Text);       // no word boxes; take what there is
                continue;
            }

            double? lastBaseline = null;
            foreach (var word in words)
            {
                var baseline = word.BoundingBox.Bottom;
                // A different baseline means a new line. The tolerance absorbs the
                // sub-point jitter within a single line of text.
                if (lastBaseline is { } previous && Math.Abs(previous - baseline) > 2.0)
                    sb.AppendLine();
                else if (lastBaseline is not null)
                    sb.Append(' ');

                sb.Append(word.Text);
                lastBaseline = baseline;
            }
            sb.AppendLine();
        }

        return sb.ToString();
    }

    /// <summary>A .docx is a zip; the body lives in word/document.xml. Paragraph
    /// and break elements become newlines so the layout survives.</summary>
    private static string ExtractDocx(string path)
    {
        using var zip = ZipFile.OpenRead(path);
        var entry = zip.GetEntry("word/document.xml");
        if (entry is null) return "";

        using var stream = entry.Open();
        var doc = XDocument.Load(stream);
        XNamespace w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

        var sb = new StringBuilder();
        foreach (var para in doc.Descendants(w + "p"))
        {
            foreach (var node in para.Descendants())
            {
                if (node.Name == w + "t") sb.Append(node.Value);
                else if (node.Name == w + "tab") sb.Append('\t');
                else if (node.Name == w + "br") sb.Append('\n');
            }
            sb.Append('\n');
        }
        return sb.ToString();
    }

    /// <summary>Pull Subject and the plain-text body out of a saved email.</summary>
    internal static JobPosting ParseEml(string path)
    {
        var raw = File.ReadAllText(path);
        var split = raw.IndexOf("\r\n\r\n", StringComparison.Ordinal);
        var headerEnd = split >= 0 ? split : raw.IndexOf("\n\n", StringComparison.Ordinal);
        var headerBlock = headerEnd >= 0 ? raw[..headerEnd] : raw;
        var body = headerEnd >= 0 ? raw[headerEnd..].TrimStart('\r', '\n') : "";

        // Unfold continuation lines (a header may wrap onto indented lines).
        var unfolded = Regex.Replace(headerBlock, @"\r?\n[ \t]+", " ");
        var subject = Regex.Match(unfolded, @"^Subject:\s*(.+)$",
                                  RegexOptions.Multiline | RegexOptions.IgnoreCase);

        var title = subject.Success ? subject.Groups[1].Value.Trim() : Path.GetFileNameWithoutExtension(path);
        return new JobPosting(Path.GetFileName(path), title, body.Length > 0 ? body : raw);
    }
}
