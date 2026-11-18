using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using Microsoft.Web.WebView2.Core;

namespace ColophonWin;

public partial class MainWindow : Window
{
    private readonly CommandLineTarget _target;
    private readonly AppSettings _settings = AppSettings.Load();
    private readonly ChildJob _job = new();

    private CoreWebView2Environment? _environment;
    private ServeSession? _serve;
    private bool _webReady;
    private bool _dirty;
    private string? _folder;
    private string? _currentFile;
    private string? _project;
    private string? _main;
    private int _tabs;

    public MainWindow(CommandLineTarget target)
    {
        _target = target;
        InitializeComponent();
        Theme.Apply(Theme.IsDark());
    }

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

    private void ApplyWebTheme()
    {
        var mode = Theme.IsDark() ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
        try { if (_webReady && Web.CoreWebView2 is { } core) core.Profile.PreferredColorScheme = mode; } catch { }
    }

    private void Window_PreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.Control) return;
        if (e.Key == Key.O)
        {
            e.Handled = true;
            _ = ChooseFolderAsync();
        }
    }

    private async void OpenFolder_Click(object sender, RoutedEventArgs e) => await ChooseFolderAsync();

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
        _folder = full;
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
            "<p><b>Ctrl+O</b> opens a folder.</p>" +
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

    protected override void OnClosed(EventArgs e)
    {
        StopServe();
        _job.Dispose();
        try { Web.Dispose(); } catch { }
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
    if ((e.key || '').toLowerCase() === 'o') {
      e.preventDefault();
      e.stopPropagation();
      window.chrome.webview.postMessage({ type: 'command', command: 'openFolder' });
    }
  }, true);
})();
""";
}
