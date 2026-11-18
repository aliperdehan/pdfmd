using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace ColophonWin;

public partial class MainWindow : Window
{
    private CoreWebView2Environment? _environment;
    private bool _webReady;

    public MainWindow()
    {
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
        ShowWelcome();
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
        ApplyWebTheme();
        _webReady = true;
    }

    private void ApplyWebTheme()
    {
        var mode = Theme.IsDark() ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
        try { if (_webReady && Web.CoreWebView2 is { } core) core.Profile.PreferredColorScheme = mode; } catch { }
    }

    private void ShowWelcome()
    {
        if (!_webReady) return;
        Web.CoreWebView2.NavigateToString(Page(
            "Colophon",
            "<p>The Windows shell for the studio is being prepared.</p>" +
            "<p class='dim'>This trial is a thin native frame around the web UI and <code>pdfmd --serve</code>.</p>"));
        StatusText.Text = "No folder open.";
    }

    private static string Page(string title, string body) =>
        "<!doctype html><meta charset=\"utf-8\"><title>" + System.Net.WebUtility.HtmlEncode(title) + "</title>" +
        "<style>html{font:15px 'Segoe UI',sans-serif;padding:2em;color:#1b1b1b;background:#f3f3f3}" +
        "pre{white-space:pre-wrap;background:#fff;border:1px solid #d6d6d6;padding:1em}" +
        ".dim{color:#666}@media(prefers-color-scheme:dark){html{color:#f0f0f0;background:#202020}" +
        "pre{background:#1b1b1b;border-color:#3c3c3c}.dim{color:#a0a0a0}}</style><h2>" +
        System.Net.WebUtility.HtmlEncode(title) + "</h2>" + body;

    protected override void OnClosed(EventArgs e)
    {
        try { Web.Dispose(); } catch { }
        base.OnClosed(e);
    }
}
