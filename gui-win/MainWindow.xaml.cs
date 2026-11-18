using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace ColophonWin;

public partial class MainWindow : Window
{
    private readonly CommandLineTarget _target;
    private readonly AppSettings _settings = AppSettings.Load();
    private readonly ChildJob _job = new();

    private CoreWebView2Environment? _environment;
    private ServeSession? _serve;
    private CancellationTokenSource? _build;
    private bool _webReady;
    private bool _pdfReady;
    private bool _pdfFailed;
    private bool _building;
    private bool _dirty;
    private string? _folder;
    private string? _currentFile;
    private string? _project;
    private string? _main;
    private string? _lastPdf;
    private int _tabs;

    public MainWindow(CommandLineTarget target)
    {
        _target = target;
        InitializeComponent();
        Theme.Apply(Theme.IsDark());
    }

    internal bool IsSmoke { get; set; }
    internal bool WebReady => _webReady;
    internal string? CurrentFile => _currentFile;
    internal string? ProjectName => _project;
    internal string? PdfShown => _lastPdf;
    internal bool Dirtied => _dirty;
    internal string BuildLog => LogText.Text;
    internal int? ServePid => _serve?.Process.Id;
    internal string? Folder => _folder;
    internal Microsoft.Web.WebView2.Core.CoreWebView2? Browser => _webReady ? Web.CoreWebView2 : null;
    internal Microsoft.Web.WebView2.Wpf.WebView2 PdfBrowser => PdfWeb;

    public async Task StartAsync()
    {
        try
        {
            await InitializeWebAsync();
        }
        catch (Exception ex)
        {
            StatusText.Text = "WebView2 could not start.";
            MessageBox.Show(this, "Colophon needs the Microsoft Edge WebView2 runtime, which Windows 11 has by default.\n\n" + ex.Message,
                            "Colophon", MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }

        if (_target.Folder is not null) await OpenFolderAsync(_target.Folder, _target.File);
        else ShowWelcome();
    }

    private async Task InitializeWebAsync()
    {
        _environment = await CoreWebView2Environment.CreateAsync(null, AppPaths.WebViewDataDir);
        await Web.EnsureCoreWebView2Async(_environment);
        var core = Web.CoreWebView2;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreDefaultContextMenusEnabled = true;
        core.Settings.IsZoomControlEnabled = true;
        await core.AddScriptToExecuteOnDocumentCreatedAsync(NativeScript);
        core.WebMessageReceived += OnWebMessage;
        core.NewWindowRequested += OnNewWindow;
        core.PermissionRequested += (_, e) => { e.State = CoreWebView2PermissionState.Deny; e.Handled = true; };
        ApplyWebTheme();
        _webReady = true;
    }

    private async Task EnsurePdfAsync()
    {
        if (_pdfReady || _pdfFailed) return;
        if (_environment is null) { _pdfFailed = true; return; }
        try
        {
            await PdfWeb.EnsureCoreWebView2Async(_environment);
            var core = PdfWeb.CoreWebView2;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = true;
            ApplyWebTheme();
            _pdfReady = true;
        }
        catch (Exception ex)
        {
            _pdfFailed = true;
            AppendLog("The PDF pane could not start: " + ex.Message);
        }
    }

    private void ApplyWebTheme()
    {
        var mode = Theme.IsDark() ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
        try { if (_webReady && Web.CoreWebView2 is { } core) core.Profile.PreferredColorScheme = mode; } catch { }
        try { if (_pdfReady && PdfWeb.CoreWebView2 is { } core) core.Profile.PreferredColorScheme = mode; } catch { }
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.Control) return;
        if (e.Key == Key.O)
        {
            e.Handled = true;
            _ = ChooseFolderAsync();
        }
        else if (e.Key == Key.B)
        {
            e.Handled = true;
            _ = BuildAsync();
        }
    }

    private async void OpenFolder_Click(object sender, RoutedEventArgs e) => await ChooseFolderAsync();
    private async void Build_Click(object sender, RoutedEventArgs e) => await BuildAsync();

    private async Task ChooseFolderAsync()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "Open a folder in Colophon",
            Multiselect = false
        };
        if (_folder is not null && Directory.Exists(_folder)) dialog.InitialDirectory = _folder;
        if (dialog.ShowDialog(this) != true) return;
        await OpenFolderAsync(dialog.FolderName, null);
    }

    internal async Task OpenFolderAsync(string folder, string? file)
    {
        var full = Path.GetFullPath(folder);
        if (!Directory.Exists(full))
        {
            ShowError("That folder does not exist", full);
            return;
        }

        StopServe();
        HideBuildPane();
        _folder = full;
        _lastPdf = null;
        _currentFile = null;
        _project = new DirectoryInfo(full).Name;
        _main = null;
        _tabs = 0;
        _dirty = false;
        ProjectLabel.Text = _project;
        StatusText.Text = "Starting pdfmd --serve …";

        try
        {
            _serve = await ServeSession.StartAsync(full, _job, Math.Max(3, _settings.ServerStartTimeoutSeconds), CancellationToken.None);
            _serve.Stopped += OnServeStopped;
            var url = _serve.Info.Url;
            if (!string.IsNullOrEmpty(file))
            {
                var relative = file.Replace('\\', '/').TrimStart('/');
                url += (url.Contains('?') ? "&" : "?") + "open=" + Uri.EscapeDataString(relative);
            }
            Web.CoreWebView2.Navigate(url);
            StatusText.Text = $"pdfmd --serve on 127.0.0.1:{_serve.Info.Port}";
        }
        catch (Exception ex)
        {
            _serve = null;
            ShowError("The studio could not start", ex.Message);
            StatusText.Text = "pdfmd --serve did not start.";
        }
    }

    private void OnServeStopped(int code)
    {
        Dispatcher.BeginInvoke(() =>
        {
            StatusText.Text = $"pdfmd --serve stopped (exit status {code}).";
        });
    }

    private void StopServe()
    {
        _build?.Cancel();
        if (_serve is null) return;
        _serve.Stopped -= OnServeStopped;
        _serve.Dispose();
        _serve = null;
    }

    private void ShowWelcome()
    {
        if (!_webReady) return;
        Web.CoreWebView2.NavigateToString(Page(
            "Colophon",
            "<p>Open a folder to work on its Markdown with the web studio.</p>" +
            "<p><b>Ctrl+O</b> opens a folder. <b>Ctrl+B</b> builds the file the studio is on.</p>" +
            "<p class='dim'>The page is served by <code>pdfmd --serve</code> on 127.0.0.1. Its server stops with this window.</p>"));
        StatusText.Text = "No folder open.";
    }

    private void ShowError(string title, string detail)
    {
        if (!_webReady)
        {
            MessageBox.Show(this, detail, title, MessageBoxButton.OK, MessageBoxImage.Error);
            return;
        }
        Web.CoreWebView2.NavigateToString(Page(title,
            "<pre>" + System.Net.WebUtility.HtmlEncode(detail) + "</pre>"));
    }

    private static string Page(string title, string body) =>
        "<!doctype html><meta charset=\"utf-8\"><title>" + System.Net.WebUtility.HtmlEncode(title) + "</title>" +
        "<style>html{font:15px 'Segoe UI',sans-serif;padding:2em;color:#1b1b1b;background:#f3f3f3}" +
        "pre{white-space:pre-wrap;background:#fff;border:1px solid #d6d6d6;padding:1em}" +
        ".dim{color:#666}@media(prefers-color-scheme:dark){html{color:#f0f0f0;background:#202020}" +
        "pre{background:#1b1b1b;border-color:#3c3c3c}.dim{color:#a0a0a0}}</style><h2>" +
        System.Net.WebUtility.HtmlEncode(title) + "</h2>" + body;

    private async void OnWebMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            using var document = JsonDocument.Parse(e.WebMessageAsJson);
            var root = document.RootElement;
            var type = root.TryGetProperty("type", out var t) ? t.GetString() : null;
            if (type == "command")
            {
                var command = root.TryGetProperty("command", out var c) ? c.GetString() : null;
                if (command == "openFolder") await ChooseFolderAsync();
                else if (command == "build") await BuildAsync();
                return;
            }
            if (type != "state") return;

            _dirty = root.TryGetProperty("dirty", out var d) && d.ValueKind == JsonValueKind.True;
            _tabs = root.TryGetProperty("tabs", out var n) && n.TryGetInt32(out var tabs) ? tabs : 0;
            _currentFile = root.TryGetProperty("cur", out var cur) && cur.ValueKind == JsonValueKind.String ? cur.GetString() : null;
            _project = root.TryGetProperty("project", out var project) && project.ValueKind == JsonValueKind.String
                ? project.GetString() : _project;
            _main = root.TryGetProperty("main", out var main) && main.ValueKind == JsonValueKind.String ? main.GetString() : _main;
            UpdateTitle();
        }
        catch (JsonException)
        {
        }
    }

    private void UpdateTitle()
    {
        var file = string.IsNullOrEmpty(_currentFile) ? null : _currentFile;
        var project = string.IsNullOrEmpty(_project) ? null : _project;
        var name = file is not null && project is not null ? $"{file} — {project}" : file ?? project ?? "Colophon";
        Title = _dirty ? name + " *" : name;
        ProjectLabel.Text = project ?? "";
        StateText.Text = file is null ? (_tabs > 0 ? $"{_tabs} tabs" : "") : file;
    }

    private void OnNewWindow(object? sender, CoreWebView2NewWindowRequestedEventArgs e)
    {
        e.Handled = true;
        if (Uri.TryCreate(e.Uri, UriKind.Absolute, out var uri) && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps))
        {
            try { Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true }); } catch { }
        }
    }

    internal async Task BuildAsync()
    {
        if (_building) return;
        if (!_webReady || _serve is null)
        {
            StatusText.Text = "Open a folder before building.";
            return;
        }
        if (!await SavePageAsync())
        {
            StatusText.Text = "Build cancelled: the page could not save the file.";
            ShowBuildPane();
            SelectPane(pdf: false);
            AppendLog("Build cancelled: the page has changes that could not be saved. A file may have changed on disk.");
            return;
        }

        var relative = _currentFile ?? _main;
        if (string.IsNullOrEmpty(relative))
        {
            StatusText.Text = "Build cancelled: the studio is on no file.";
            return;
        }
        if (!IsText(relative))
        {
            StatusText.Text = "Build cancelled: " + relative + " is not a text file.";
            return;
        }

        var root = _folder;
        if (root is null) return;
        string file;
        try { file = Path.GetFullPath(Path.Combine(root, relative.Replace('/', '\\'))); }
        catch (Exception ex)
        {
            StatusText.Text = "Build cancelled: " + ex.Message;
            return;
        }
        if (!file.StartsWith(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                             StringComparison.OrdinalIgnoreCase) || !File.Exists(file))
        {
            StatusText.Text = "Build cancelled: " + relative + " is not in this folder.";
            return;
        }

        var working = Path.GetDirectoryName(file)!;
        var argument = Path.GetFileName(file);
        _building = true;
        BuildButton.IsEnabled = false;
        _build = new CancellationTokenSource();
        ShowBuildPane();
        SelectPane(pdf: false);
        LogText.Clear();
        PaneTitle.Text = "Build log: " + argument;

        try
        {
            var command = PdfmdLocator.Find();
            var shown = PdfmdLocator.Display(command, working, new[] { argument });
            AppendLog("$ " + shown);
            StatusText.Text = "Building " + argument + " …";
            var outcome = await BuildRunner.RunAsync(command, working, argument, root, _job,
                Math.Max(30, _settings.BuildTimeoutSeconds),
                line => Dispatcher.BeginInvoke(() => AppendLog(line)),
                _build.Token);

            if (outcome.Ok)
            {
                if (outcome.PdfPath is not null)
                {
                    await ShowPdfAsync(outcome.PdfPath);
                    StatusText.Text = $"Built {Path.GetFileName(outcome.PdfPath)} in {outcome.Seconds:0.0} s.";
                }
                else
                {
                    SelectPane(pdf: false);
                    StatusText.Text = "pdfmd finished but named no PDF. See the log.";
                    AppendLog("pdfmd exited 0 but no PDF was found.");
                }
            }
            else
            {
                SelectPane(pdf: false);
                var why = outcome.CouldNotStart ? outcome.Error
                    : outcome.TimedOut ? outcome.Error
                    : "exit status " + outcome.ExitCode;
                StatusText.Text = "Build failed (" + why + "). See the log.";
                AppendLog("");
                AppendLog("BUILD FAILED: " + why);
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            SelectPane(pdf: false);
            StatusText.Text = "Build failed. See the log.";
            AppendLog("BUILD FAILED: " + ex.Message);
        }
        finally
        {
            _building = false;
            BuildButton.IsEnabled = true;
            _build?.Dispose();
            _build = null;
        }
    }

    internal static bool IsText(string path)
    {
        var extension = Path.GetExtension(path).ToLowerInvariant();
        return extension is not (".pdf" or ".png" or ".jpg" or ".jpeg" or ".gif" or ".svg" or ".webp");
    }

    private async Task<bool> SavePageAsync()
    {
        if (!_webReady) return true;
        var dirty = await EvalBoolAsync("window.appDirty ? window.appDirty() : null");
        if (dirty != true) return true;
        await EvalAsync("window.appSave && window.appSave().catch(function(){})");
        var deadline = DateTime.UtcNow.AddSeconds(Math.Max(3, _settings.SaveTimeoutSeconds));
        while (DateTime.UtcNow < deadline)
        {
            await Task.Delay(150);
            var still = await EvalBoolAsync("window.appDirty ? window.appDirty() : null");
            if (still == false) return true;
        }
        return false;
    }

    internal async Task<bool?> EvalBoolAsync(string script)
    {
        var raw = await EvalAsync(script);
        return raw switch
        {
            "true" => true,
            "false" => false,
            _ => null
        };
    }

    internal async Task<string?> EvalAsync(string script)
    {
        if (!_webReady) return null;
        try { return await Web.CoreWebView2.ExecuteScriptAsync(script); }
        catch { return null; }
    }

    private void ShowBuildPane()
    {
        if (BuildPane.Visibility == Visibility.Visible) return;
        SplitterRow.Height = new GridLength(5);
        PaneRow.Height = new GridLength(Math.Max(120, _settings.BuildPaneHeight));
        BuildSplitter.Visibility = Visibility.Visible;
        BuildPane.Visibility = Visibility.Visible;
    }

    private void HideBuildPane()
    {
        BuildPane.Visibility = Visibility.Collapsed;
        BuildSplitter.Visibility = Visibility.Collapsed;
        PaneRow.Height = new GridLength(0);
        SplitterRow.Height = new GridLength(0);
    }

    private void ClosePane_Click(object sender, RoutedEventArgs e) => HideBuildPane();
    private void PdfTab_Click(object sender, RoutedEventArgs e) => SelectPane(pdf: true);
    private void LogTab_Click(object sender, RoutedEventArgs e) => SelectPane(pdf: false);

    private void SelectPane(bool pdf)
    {
        PdfWeb.Visibility = pdf ? Visibility.Visible : Visibility.Collapsed;
        LogText.Visibility = pdf ? Visibility.Collapsed : Visibility.Visible;
        PdfTab.Foreground = (Brush)FindResource(pdf ? "AccentBrush" : "MutedBrush");
        LogTab.Foreground = (Brush)FindResource(pdf ? "MutedBrush" : "AccentBrush");
    }

    private async Task ShowPdfAsync(string path)
    {
        await EnsurePdfAsync();
        ShowBuildPane();
        if (!_pdfReady)
        {
            SelectPane(pdf: false);
            AppendLog("The PDF pane is not available; the build still wrote " + path);
            return;
        }
        SelectPane(pdf: true);
        PaneTitle.Text = $"PDF: {Path.GetFileName(path)}";
        if (string.Equals(_lastPdf, path, StringComparison.OrdinalIgnoreCase))
        {
            PdfWeb.CoreWebView2.Reload();
        }
        else
        {
            _lastPdf = path;
            PdfWeb.CoreWebView2.Navigate(new Uri(path).AbsoluteUri);
        }
    }

    internal void CloseForSmoke()
    {
        Close();
    }

    private void AppendLog(string line)
    {
        LogText.AppendText(line + Environment.NewLine);
        LogText.ScrollToEnd();
    }

    protected override void OnClosed(EventArgs e)
    {
        StopServe();
        _job.Dispose();
        try { Web.Dispose(); } catch { }
        try { PdfWeb.Dispose(); } catch { }
        base.OnClosed(e);
    }

    private const string NativeScript = """
(function () {
  if (!window.chrome || !window.chrome.webview) return;
  window.webkit = window.webkit || {};
  window.webkit.messageHandlers = window.webkit.messageHandlers || {};
  if (!window.webkit.messageHandlers.colophon) {
    window.webkit.messageHandlers.colophon = {
      postMessage: function (m) { window.chrome.webview.postMessage(m); }
    };
  }
  window.addEventListener('keydown', function (e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
    var k = (e.key || '').toLowerCase();
    if (k === 'o' || k === 'b') {
      e.preventDefault();
      e.stopPropagation();
      window.chrome.webview.postMessage({ type: 'command', command: k === 'o' ? 'openFolder' : 'build' });
    }
  }, true);
})();
""";
}
