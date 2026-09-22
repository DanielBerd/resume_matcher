using System.Diagnostics;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using ResumeMatcher.Core.Models;
using ResumeMatcher.Core.Services;

namespace ResumeMatcher.App;

public partial class MainWindow : Window
{
    private AppSettings _settings = AppSettings.Load();
    private CancellationTokenSource? _run;
    private string? _lastReport;
    private bool _busy;

    public MainWindow()
    {
        InitializeComponent();
        _settings.EnsureFolders();

        PresetBox.ItemsSource = Provider.All.Select(p => p.Name).ToList();
        LoadSettingsIntoFields();
        RefreshSummary();

        // Real drag-and-drop, built into the framework — no optional extra.
        DragDrop.SetAllowDrop(DropZone, true);
        DropZone.AddHandler(DragDrop.DragEnterEvent, OnDragEnter);
        DropZone.AddHandler(DragDrop.DragLeaveEvent, OnDragLeave);
        DropZone.AddHandler(DragDrop.DropEvent, OnDrop);

        // A local server is cheap to ask; a hosted catalogue is fetched on demand.
        if (!_settings.IsHosted) _ = FetchModelsAsync(quiet: true);
    }

    // ---------- settings <-> fields ----------

    private void LoadSettingsIntoFields()
    {
        PresetBox.SelectedItem = Provider.Find(_settings.Provider)?.Name ?? Provider.All[0].Name;
        LocalRadio.IsChecked = !_settings.IsHosted;
        HostedRadio.IsChecked = _settings.IsHosted;
        BaseUrlBox.Text = _settings.BaseUrl;
        ApiKeyBox.Text = _settings.ApiKey;
        ModelBox.ItemsSource ??= new List<string>();
        SetModelText(_settings.Model);
        ConcurrencyBox.Value = _settings.Concurrency;
        UpdatePrivacyNote();
    }

    /// <summary>What is on the Server tab is what a run uses.</summary>
    private AppSettings ReadFields()
    {
        _settings.Mode = HostedRadio.IsChecked == true ? LlmMode.Hosted : LlmMode.Local;
        _settings.Provider = PresetBox.SelectedItem as string ?? _settings.Provider;
        _settings.BaseUrl = BaseUrlBox.Text?.Trim() ?? "";
        _settings.ApiKey = ApiKeyBox.Text ?? "";
        _settings.Model = (ModelBox.SelectedItem as string ?? ModelBox.Text ?? "").Trim();
        _settings.Concurrency = (int)(ConcurrencyBox.Value ?? 4);
        return _settings;
    }

    private void SetModelText(string model)
    {
        var items = (ModelBox.ItemsSource as IEnumerable<string>)?.ToList() ?? [];
        if (items.Contains(model)) ModelBox.SelectedItem = model;
        ModelBox.Text = model;
    }

    private void OnPresetChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (PresetBox.SelectedItem is not string name || Provider.Find(name) is not { } p) return;
        if (!IsLoaded) return;

        HostedRadio.IsChecked = p.Mode == LlmMode.Hosted;
        LocalRadio.IsChecked = p.Mode == LlmMode.Local;
        if (p.BaseUrl.Length > 0) BaseUrlBox.Text = p.BaseUrl;
        if (p.Model.Length > 0) SetModelText(p.Model);
        if (!p.NeedsKey) ApiKeyBox.Text = "local";
        UpdatePrivacyNote();
        RefreshSummary();
    }

    private void OnModeChanged(object? sender, RoutedEventArgs e)
    {
        if (!IsLoaded) return;
        UpdatePrivacyNote();
        RefreshSummary();
    }

    private void OnModelChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (IsLoaded) RefreshSummary();
    }

    private void OnShowKeyChanged(object? sender, RoutedEventArgs e) =>
        ApiKeyBox.PasswordChar = ShowKey.IsChecked == true ? '\0' : '●';

    private void UpdatePrivacyNote()
    {
        var hosted = HostedRadio.IsChecked == true;
        PrivacyNote.IsVisible = hosted;
        PrivacyNote.Text = hosted
            ? "Hosted API: every job posting and the full text of every resume is sent to this provider. "
              + "Resumes are personal data — use this knowingly."
            : "";
    }

    // ---------- summary line ----------

    private void RefreshSummary()
    {
        var hosted = HostedRadio.IsChecked == true;
        var model = (ModelBox.Text ?? "").Trim();
        var host = Uri.TryCreate(BaseUrlBox.Text ?? "", UriKind.Absolute, out var uri) ? uri.Host : BaseUrlBox.Text;

        Summary.Text = $"Using {(model.Length > 0 ? model : "(no model set)")} @ {host} "
                     + $"({(hosted ? "hosted — data leaves this PC" : "local")})";
        Summary.Foreground = Brush(hosted ? "WarningBrush" : "MutedBrush");
    }

    private void OnSummaryClicked(object? sender, PointerPressedEventArgs e) => Tabs.SelectedIndex = 1;

    // ---------- drag and drop ----------

    private void OnDragEnter(object? sender, DragEventArgs e)
    {
        if (!e.Data.Contains(DataFormats.Files)) return;
        DropZone.Background = Brush("ZoneHoverBrush");
    }

    private void OnDragLeave(object? sender, DragEventArgs e) => ResetDropZone();

    private void ResetDropZone() => DropZone.Background = Brush("ZoneBrush");

    private async void OnDrop(object? sender, DragEventArgs e)
    {
        ResetDropZone();
        var file = e.Data.GetFiles()?.FirstOrDefault();
        var path = file?.TryGetLocalPath();
        if (path is not null) await RunAsync(path);
    }

    private async void OnBrowseJob(object? sender, PointerPressedEventArgs e)
    {
        if (_busy) return;

        var picked = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose a job posting",
            AllowMultiple = false,
            FileTypeFilter =
            [
                new FilePickerFileType("Job postings") { Patterns = ["*.txt", "*.md", "*.eml", "*.pdf", "*.docx"] },
                new FilePickerFileType("All files") { Patterns = ["*"] },
            ],
        });

        var path = picked.FirstOrDefault()?.TryGetLocalPath();
        if (path is not null) await RunAsync(path);
    }

    // ---------- running ----------

    private async void OnRunAll(object? sender, RoutedEventArgs e) => await RunAsync(null);

    private void OnCancel(object? sender, RoutedEventArgs e)
    {
        _run?.Cancel();
        SetStatus("Stopping…");
    }

    private async Task RunAsync(string? singleJob)
    {
        if (_busy) return;

        var settings = ReadFields();
        if (string.IsNullOrWhiteSpace(settings.Model))
        {
            SetStatus("Set a model on the Server tab first.", error: true);
            Tabs.SelectedIndex = 1;
            return;
        }

        settings.Save();
        settings.EnsureFolders();
        SetBusy(true);
        Log.Text = "";
        Progress.Value = 0;
        _run = new CancellationTokenSource();

        try
        {
            using var client = new LlmClient(settings);

            // Check the server before scoring anything, so a stopped server fails
            // in a second rather than once per resume.
            SetStatus("Checking the server…");
            await client.ListModelsAsync(_run.Token);

            var resumes = DocumentReader.LoadResumes(settings.Resumes);
            if (resumes.Count == 0)
                throw new InvalidOperationException($"No resumes found in {settings.Resumes}");

            var jobs = singleJob is not null
                ? [DocumentReader.TryLoadJob(singleJob) ?? throw new InvalidOperationException($"Could not read {singleJob}")]
                : DocumentReader.LoadJobs(settings.Jobs);
            if (jobs.Count == 0)
                throw new InvalidOperationException($"No job postings found in {settings.Jobs}");

            Append($"Matching {jobs.Count} job(s) against {resumes.Count} resume(s) using {settings.Model} @ {client.Host}");
            SetStatus("Working…");

            var progress = new Progress<MatchProgress>(p =>
            {
                Progress.Value = p.Fraction;
                Append(p.Message);
            });

            var results = await new Matcher(settings, client).RunAsync(jobs, resumes, progress, _run.Token);

            _lastReport = ReportWriter.Write(results, settings.Results);
            Append($"Report saved to {_lastReport}");
            OpenReportButton.IsEnabled = true;
            Progress.Value = 1;
            SetStatus($"Done — {Path.GetFileName(_lastReport)}");
            Open(_lastReport);
        }
        catch (OperationCanceledException)
        {
            SetStatus("Stopped.");
            Append("Stopped before finishing.");
        }
        catch (Exception ex)
        {
            SetStatus(ex.Message, error: true);
            Append($"Error: {ex.Message}");
            if (ex is LlmException) Tabs.SelectedIndex = 1;
        }
        finally
        {
            _run?.Dispose();
            _run = null;
            SetBusy(false);
        }
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        RunAllButton.IsEnabled = !busy;
        CancelButton.IsEnabled = busy;
        FetchButton.IsEnabled = !busy;
    }

    // ---------- server tab actions ----------

    private async void OnFetchModels(object? sender, RoutedEventArgs e) => await FetchModelsAsync(quiet: false);

    private async void OnTestConnection(object? sender, RoutedEventArgs e) => await FetchModelsAsync(quiet: false);

    private async Task FetchModelsAsync(bool quiet)
    {
        var settings = ReadFields();
        if (string.IsNullOrWhiteSpace(settings.BaseUrl)) return;

        if (!quiet) SetServerStatus("Connecting…");
        try
        {
            using var client = new LlmClient(settings);
            var models = await client.ListModelsAsync();

            ModelBox.ItemsSource = models;
            if (!settings.IsHosted && models.Count > 0)
                SetModelText(Provider.PickDefaultModel(models, settings.Model));

            SetServerStatus($"Connected — {models.Count} model(s): {string.Join(", ", models.Take(6))}"
                            + (models.Count > 6 ? " …" : ""), ok: true);
            RefreshSummary();
        }
        catch (Exception ex)
        {
            if (!quiet) SetServerStatus(ex.Message, error: true);
            else SetServerStatus($"Not connected: {ex.Message}");
        }
    }

    private void OnSave(object? sender, RoutedEventArgs e)
    {
        ReadFields().Save();
        RefreshSummary();
        SetServerStatus($"Saved to {AppSettings.SettingsPath}", ok: true);
    }

    private void OnOpenFolders(object? sender, RoutedEventArgs e)
    {
        _settings.EnsureFolders();
        Open(AppSettings.DefaultRoot);
    }

    private void OnOpenReport(object? sender, RoutedEventArgs e)
    {
        if (_lastReport is not null) Open(_lastReport);
    }

    /// <summary>Hand a path to the shell, which opens it in whatever is registered.</summary>
    private static void Open(string path)
    {
        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
        catch (Exception) { /* no handler registered; nothing useful to do */ }
    }

    // ---------- small UI helpers ----------

    /// <summary>Look up one of the app's theme brushes for the variant in force.
    /// Falls back to the default text colour rather than null, which would make
    /// the text invisible.</summary>
    private IBrush Brush(string key) =>
        this.TryFindResource(key, ActualThemeVariant, out var value) && value is IBrush brush
            ? brush
            : Foreground ?? Brushes.Gray;

    private void Append(string line) => Dispatcher.UIThread.Post(() =>
    {
        Log.Text += (Log.Text?.Length > 0 ? "\n" : "") + line;
        LogScroller.ScrollToEnd();
    });

    private void SetStatus(string text, bool error = false)
    {
        Status.Text = text;
        Status.Foreground = Brush(error ? "DangerBrush" : "MutedBrush");
    }

    private void SetServerStatus(string text, bool ok = false, bool error = false)
    {
        ServerStatus.Text = text;
        ServerStatus.Foreground = Brush(error ? "DangerBrush" : ok ? "SuccessBrush" : "MutedBrush");
    }
}
