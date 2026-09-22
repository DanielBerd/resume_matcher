using System.IO.Compression;
using System.Text;
using ResumeMatcher.Core.Services;
using Xunit;

namespace ResumeMatcher.Tests;

public class DocumentReaderTests : IDisposable
{
    private readonly string _dir = Directory.CreateTempSubdirectory("rm-tests").FullName;

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private string Write(string name, string content)
    {
        var path = Path.Combine(_dir, name);
        File.WriteAllText(path, content);
        return path;
    }

    [Fact]
    public void ReadsDocxParagraphsAsLines()
    {
        var path = Path.Combine(_dir, "resume.docx");
        using (var zip = ZipFile.Open(path, ZipArchiveMode.Create))
        {
            var entry = zip.CreateEntry("word/document.xml");
            using var writer = new StreamWriter(entry.Open(), Encoding.UTF8);
            writer.Write("""
                <?xml version="1.0"?>
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body>
                    <w:p><w:r><w:t>Anna Kovacs</w:t></w:r></w:p>
                    <w:p><w:r><w:t>Senior Python</w:t><w:br/><w:t>Engineer</w:t></w:r></w:p>
                  </w:body>
                </w:document>
                """);
        }

        var text = DocumentReader.TryExtract(path);
        Assert.Contains("Anna Kovacs", text);
        Assert.Contains("Senior Python", text);
        // The <w:br/> became a newline rather than gluing the words together.
        Assert.DoesNotContain("PythonEngineer", text);
    }

    [Fact]
    public void KeepsTheSubjectOfAnEmailAsTheJobTitle()
    {
        var path = Write("job.eml",
            "From: jobs@example.com\r\nSubject: Senior Python Engineer\r\nDate: today\r\n\r\nWe need Python and Azure.\r\n");

        var job = DocumentReader.TryLoadJob(path);

        Assert.NotNull(job);
        Assert.Equal("Senior Python Engineer", job!.Title);
        Assert.Contains("Python and Azure", job.Body);
        Assert.DoesNotContain("jobs@example.com", job.Body);   // headers stay out of the prompt
    }

    [Fact]
    public void UnfoldsHeadersThatWrapOntoTheNextLine()
    {
        var path = Write("wrapped.eml",
            "Subject: Senior Python Engineer\r\n  (Remote, EU)\r\nFrom: a@b.c\r\n\r\nBody here.\r\n");

        Assert.Equal("Senior Python Engineer (Remote, EU)", DocumentReader.TryLoadJob(path)!.Title);
    }

    [Fact]
    public void UsesTheFirstLineOfAPlainTextPostingAsItsTitle()
    {
        var path = Write("job.txt", "\n\nData Engineer\n\nYou will build pipelines.\n");
        Assert.Equal("Data Engineer", DocumentReader.TryLoadJob(path)!.Title);
    }

    [Fact]
    public void SkipsUnsupportedAndEmptyFiles()
    {
        Write("notes.xyz", "ignored");
        Write("blank.txt", "   \n  ");
        Write("real.txt", "A real resume with text.");

        var resumes = DocumentReader.LoadResumes(_dir);

        Assert.Single(resumes);
        Assert.Equal("real.txt", resumes[0].Name);
    }

    [Fact]
    public void AnUnreadableFileReturnsEmptyRatherThanThrowing() =>
        Assert.Equal("", DocumentReader.TryExtract(Path.Combine(_dir, "does-not-exist.pdf")));
}
