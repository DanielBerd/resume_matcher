using System.Net;
using System.Text;
using System.Text.Json;

namespace ResumeMatcher.Tests;

/// <summary>
/// A real HTTP server on a loopback port, standing in for an OpenAI-compatible
/// model server. Using a socket rather than a mocked handler means the client's
/// timeout, status handling and JSON round-trip are all genuinely exercised.
/// </summary>
public sealed class FakeServer : IDisposable
{
    private readonly HttpListener _listener = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly List<string> _bodies = [];
    private int _calls;

    /// <summary>Set to shape the next chat reply. Return null to use the default.</summary>
    public Func<int, (HttpStatusCode Status, string Body)?>? OnChat { get; set; }

    public string[] Models { get; set; } = ["gemma-4-12b-it-qat", "gemma-4-e4b-it-qat"];

    /// <summary>Highest number of chat requests in flight at the same time.</summary>
    public int PeakConcurrency { get; private set; }

    private int _inFlight;
    private readonly object _lock = new();

    public int Calls => Volatile.Read(ref _calls);
    public IReadOnlyList<string> Bodies { get { lock (_lock) return _bodies.ToList(); } }
    public string BaseUrl { get; }

    public FakeServer()
    {
        var port = GetFreePort();
        BaseUrl = $"http://127.0.0.1:{port}/v1";
        _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
        _listener.Start();
        _ = Task.Run(LoopAsync);
    }

    private static int GetFreePort()
    {
        var l = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }

    private async Task LoopAsync()
    {
        while (!_cts.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await _listener.GetContextAsync(); }
            catch (Exception) { return; }
            _ = Task.Run(() => HandleAsync(ctx));
        }
    }

    private async Task HandleAsync(HttpListenerContext ctx)
    {
        var path = ctx.Request.Url!.AbsolutePath;

        if (path.EndsWith("/models", StringComparison.Ordinal))
        {
            var payload = JsonSerializer.Serialize(new { data = Models.Select(m => new { id = m }).ToArray() });
            await RespondAsync(ctx, HttpStatusCode.OK, payload);
            return;
        }

        using (var reader = new StreamReader(ctx.Request.InputStream, Encoding.UTF8))
        {
            var body = await reader.ReadToEndAsync();
            lock (_lock) _bodies.Add(body);
        }

        var n = Interlocked.Increment(ref _calls);
        var now = Interlocked.Increment(ref _inFlight);
        lock (_lock) PeakConcurrency = Math.Max(PeakConcurrency, now);

        try
        {
            var custom = OnChat?.Invoke(n);
            if (custom is { } c)
            {
                await RespondAsync(ctx, c.Status, c.Body);
                return;
            }

            await Task.Delay(40);   // long enough for overlap to be observable
            await RespondAsync(ctx, HttpStatusCode.OK, ChatReply(70 + n % 25, $"Reply {n}."));
        }
        finally
        {
            Interlocked.Decrement(ref _inFlight);
        }
    }

    public static string ChatReply(int score, string comment) => JsonSerializer.Serialize(new
    {
        choices = new[]
        {
            new { finish_reason = "stop", message = new { role = "assistant", content = $"{{\"score\": {score}, \"comment\": \"{comment}\"}}" } },
        },
    });

    private static async Task RespondAsync(HttpListenerContext ctx, HttpStatusCode status, string body)
    {
        var bytes = Encoding.UTF8.GetBytes(body);
        ctx.Response.StatusCode = (int)status;
        ctx.Response.ContentType = "application/json";
        ctx.Response.ContentLength64 = bytes.Length;
        try
        {
            await ctx.Response.OutputStream.WriteAsync(bytes);
            ctx.Response.Close();
        }
        catch (HttpListenerException) { /* client gave up (timeout test) */ }
    }

    public void Dispose()
    {
        _cts.Cancel();
        try { _listener.Stop(); } catch (ObjectDisposedException) { }
        _listener.Close();
        _cts.Dispose();
    }
}
