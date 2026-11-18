using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace ColophonWin;

internal static class Smoke
{
    public static async Task<int> RunCrashAsync()
    {
        var pidFile = Environment.GetEnvironmentVariable("COLOPHON_CRASH_PIDFILE");
        if (string.IsNullOrWhiteSpace(pidFile)) return 2;

        var root = Path.Combine(Path.GetTempPath(), "colophon-win-crash-" + Guid.NewGuid().ToString("N"));
        var folder = Path.Combine(root, "project");
        var data = Path.Combine(root, "data");
        Directory.CreateDirectory(folder);
        Directory.CreateDirectory(data);
        Environment.SetEnvironmentVariable("COLOPHON_DATA_DIR", data);
        File.WriteAllText(Path.Combine(folder, "sample.md"), "# Crash test\n", new UTF8Encoding(false));

        var window = new MainWindow(new CommandLineTarget(folder, "sample.md", null))
        {
            IsSmoke = true,
            ShowInTaskbar = false,
            ShowActivated = false,
            WindowStartupLocation = WindowStartupLocation.Manual,
            Left = -32000,
            Top = -32000
        };
        window.Show();
        await window.StartAsync();
        if (!await WaitUntil(() => window.ServePid is not null, 30)) return 3;
        File.WriteAllText(pidFile, window.ServePid!.Value.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Process.GetCurrentProcess().Kill();
        await Task.Delay(5000);
        return 4;
    }

    public static async Task<int> RunAsync(string[] args)
    {
        var root = Path.Combine(Path.GetTempPath(), "colophon-win-smoke-" + Guid.NewGuid().ToString("N"));
        var folder = Path.Combine(root, "project");
        var data = Path.Combine(root, "data");
        Directory.CreateDirectory(folder);
        Directory.CreateDirectory(data);
        Environment.SetEnvironmentVariable("COLOPHON_DATA_DIR", data);
        Environment.SetEnvironmentVariable("COLOPHON_SMOKE_ROOT", root);

        var sample = Path.Combine(folder, "sample.md");
        File.WriteAllText(sample,
            "---\npdfmd-options: {pdf-engine: typst}\n---\n\n# Smoke\n\nA tiny document for the shell's own test.\n",
            new UTF8Encoding(false));

        using var log = OpenLog();
        var checks = new Checks(log ?? Console.Out, Console.Out);
        var window = new MainWindow(new CommandLineTarget(folder, "sample.md", null))
        {
            IsSmoke = true,
            ShowInTaskbar = false,
            ShowActivated = false,
            WindowStartupLocation = WindowStartupLocation.Manual,
            Left = -32000,
            Top = -32000
        };

        int? server = null;
        try
        {
            window.Show();
            await window.StartAsync();

            checks.Check("the studio page opens the file that was asked for",
                await WaitUntil(() => window.CurrentFile == "sample.md", 30),
                "cur=" + (window.CurrentFile ?? "null"));

            checks.Check("the page knows it is in a native window",
                await EvalBool(window, "window.NATIVE !== null && document.documentElement.classList.contains('native')") == true,
                "native.js did not see the bridge");

            var href = await EvalString(window, "location.href");
            checks.Check("the page is served over localhost HTTP",
                href is not null && href.StartsWith("http://127.0.0.1:", StringComparison.Ordinal),
                href ?? "no href");

            checks.Check("the page starts with nothing unsaved",
                await EvalBool(window, "window.appDirty ? window.appDirty() : null") == false,
                "appDirty was not false");

            checks.Check("the page answers a native command",
                await EvalBool(window, "window.appCommand && window.appCommand('layoutEditor')") == true,
                "appCommand('layoutEditor') was refused");

            await window.EvalAsync("window.__app.editor.replaceSelection('\\n\\nA smoke edit.', false)");
            checks.Check("a page edit shows as unsaved",
                await WaitUntilBool(window, "window.appDirty ? window.appDirty() : null", true, 5),
                "appDirty stayed false");

            await window.EvalAsync("window.appSave && window.appSave().catch(function(){})");
            checks.Check("the page saves its own edit",
                await WaitUntilBool(window, "window.appDirty ? window.appDirty() : null", false, 10),
                "appDirty stayed true");
            checks.Check("the saved text is on disk",
                File.Exists(sample) && File.ReadAllText(sample).Contains("A smoke edit.", StringComparison.Ordinal),
                "the file does not hold the edit");

            server = window.ServePid;
            await window.BuildAsync();
            checks.Check("Build writes a PDF and shows it in the pane",
                window.PdfShown is not null && File.Exists(window.PdfShown), window.PdfShown ?? "no PDF");
            checks.Check("Build finds pdfmd's own OK line",
                window.BuildLog.Contains("OK", StringComparison.Ordinal), LastLines(window.BuildLog, 6));

            if (window.PdfShown is not null && window.PdfBrowser.CoreWebView2 is not null)
            {
                await WaitUntil(() => window.PdfBrowser.Source is { IsFile: true }, 10);
                var source = window.PdfBrowser.Source;
                checks.Check("the PDF pane is on the built file",
                    source is not null && source.IsFile && string.Equals(Path.GetFullPath(source.LocalPath),
                        Path.GetFullPath(window.PdfShown), StringComparison.OrdinalIgnoreCase),
                    source?.ToString() ?? "no source");
                try
                {
                    await Task.Delay(1200);
                    using var image = new MemoryStream();
                    await window.PdfBrowser.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, image);
                    checks.Note($"the PDF pane drew {image.Length} bytes of PNG");
                }
                catch (Exception ex)
                {
                    checks.Note("the PDF pane could not be captured: " + ex.Message);
                }
            }
            else
            {
                checks.Fail("the PDF pane exists", "PdfWeb2 has no CoreWebView2");
            }

            using (var job = new ChildJob())
            {
                var bad = await BuildRunner.RunAsync(PdfmdLocator.Find(), folder, "missing.md", folder, job, 120,
                    _ => { }, CancellationToken.None);
                checks.Check("a failed build keeps its exit status and output",
                    !bad.Ok && bad.ExitCode != 0 && bad.Output.Length > 0,
                    "exit=" + bad.ExitCode + " output=" + LastLines(bad.Output, 4));
            }
        }
        catch (Exception ex)
        {
            checks.Fail("smoke run", ex.ToString());
        }
        finally
        {
            window.CloseForSmoke();
            await Task.Delay(1500);
            if (server is not null)
                checks.Check("the serve process stops with the window", !Alive(server.Value), "still running: pid " + server);
            checks.Note("data dir: " + AppPaths.DataDir);
            checks.Check("the window rectangle is remembered",
                File.Exists(AppPaths.WindowFile), "window.json is missing at " + AppPaths.WindowFile);
            try { Directory.Delete(root, true); } catch { }
        }

        checks.Note("the close prompt for unsaved changes and the visual result on screen were not verified by hand");
        return checks.Finish();
    }

    private static bool Alive(int pid)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            return !process.HasExited;
        }
        catch
        {
            return false;
        }
    }

    private static async Task<bool> WaitUntil(Func<bool> test, int seconds)
    {
        var end = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < end)
        {
            if (test()) return true;
            await Task.Delay(100);
        }
        return test();
    }

    private static async Task<bool> WaitUntilBool(MainWindow window, string script, bool wanted, int seconds)
    {
        var end = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < end)
        {
            if (await window.EvalBoolAsync(script) == wanted) return true;
            await Task.Delay(100);
        }
        return await window.EvalBoolAsync(script) == wanted;
    }

    private static async Task<bool?> EvalBool(MainWindow window, string script) => await window.EvalBoolAsync(script);

    private static async Task<string?> EvalString(MainWindow window, string script)
    {
        var raw = await window.EvalAsync(script);
        if (raw is null or "null") return null;
        try { return JsonSerializer.Deserialize<string>(raw); }
        catch (JsonException) { return raw.Trim('"'); }
    }

    private static string LastLines(string text, int count)
    {
        var lines = text.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        return string.Join(" | ", lines.TakeLast(count));
    }

    private static StreamWriter? OpenLog()
    {
        var path = Environment.GetEnvironmentVariable("COLOPHON_SMOKE_LOG");
        if (string.IsNullOrWhiteSpace(path)) return null;
        try { return new StreamWriter(path, false, new UTF8Encoding(false)) { AutoFlush = true }; }
        catch { return null; }
    }

    private sealed class Checks
    {
        private readonly TextWriter _out;
        private readonly TextWriter _console;
        private int _passed;
        private int _failed;

        public Checks(TextWriter output, TextWriter console)
        {
            _out = output;
            _console = console;
        }

        public void Check(string name, bool ok, string detail)
        {
            if (ok)
            {
                _passed++;
                Say("ok    " + name);
            }
            else
            {
                _failed++;
                Say("FAIL  " + name + ": " + detail);
            }
        }

        public void Fail(string name, string detail)
        {
            _failed++;
            Say("FAIL  " + name + ": " + detail);
        }

        public void Note(string text) => Say("note  " + text);

        private void Say(string line)
        {
            _out.WriteLine(line);
            if (!ReferenceEquals(_out, _console)) _console.WriteLine(line);
        }

        public int Finish()
        {
            Say($"{_passed} passed, {_failed} failed.");
            return _failed == 0 ? 0 : 1;
        }
    }
}
