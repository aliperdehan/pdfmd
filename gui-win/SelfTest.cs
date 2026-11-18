using System.IO;
using System.Windows;

namespace ColophonWin;

internal static class SelfTest
{
    public static int Run(TextWriter output)
    {
        var failed = 0;
        var passed = 0;

        void Check(string name, Action test)
        {
            try
            {
                test();
                passed++;
                output.WriteLine("ok    " + name);
            }
            catch (Exception ex)
            {
                failed++;
                output.WriteLine("FAIL  " + name + ": " + ex.Message);
            }
        }

        Check("command line: a folder is the project", () =>
        {
            var dir = Scratch();
            try
            {
                var target = CommandLineTarget.Parse(new[] { dir });
                Equal(dir, target.Folder, "folder");
                Equal(null, target.File, "file");
                Equal(null, target.Error, "error");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("command line: a file opens its folder on the file", () =>
        {
            var dir = Scratch();
            try
            {
                var file = Path.Combine(dir, "report.md");
                File.WriteAllText(file, "# Report");
                var target = CommandLineTarget.Parse(new[] { file });
                Equal(dir, target.Folder, "folder");
                Equal("report.md", target.File, "file");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("command line: no argument opens the welcome page", () =>
        {
            var target = CommandLineTarget.Parse(Array.Empty<string>());
            Equal(null, target.Folder, "folder");
            Equal(null, target.File, "file");
        });

        Check("command line: two words are refused", () =>
        {
            var target = CommandLineTarget.Parse(new[] { "a.md", "b.md" });
            True(target.Error is not null, "an error was expected");
        });

        Check("pdfmd: a .cmd on COLOPHON_PDFMD runs through cmd.exe", () =>
        {
            var dir = Scratch();
            try
            {
                var cmd = Path.Combine(dir, "fake pdfmd.cmd");
                File.WriteAllText(cmd, "@echo off\r\n");
                var command = PdfmdLocator.Command(cmd, "test");
                True(command.FileName.EndsWith("cmd.exe", StringComparison.OrdinalIgnoreCase), "cmd.exe");
                Equal(2, command.Prefix.Count, "two prefix words");
                Equal("/c", command.Prefix[0], "first prefix");
                Equal(cmd, command.Prefix[1], "second prefix");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("pdfmd: the child environment asks for UTF-8", () =>
        {
            var info = PdfmdLocator.StartInfo(new PdfmdCommand("pdfmd.exe", Array.Empty<string>(), "test"), "C:\\", "--serve", "x");
            Equal("1", info.Environment["PYTHONUTF8"], "PYTHONUTF8");
            Equal("utf-8", info.Environment["PYTHONIOENCODING"], "PYTHONIOENCODING");
            Equal(2, info.ArgumentList.Count, "arguments");
        });

        Check("build: the PDF after the time and the engine is found", () =>
        {
            var dir = Scratch();
            try
            {
                var pdf = Path.Combine(dir, "report.pdf");
                File.WriteAllText(pdf, "pdf");
                var found = BuildRunner.FindMadePdf(
                    "DEFAULTS  margin\nOK    report.md > report.pdf  in 3:07  (lualatex)\n", "report.md", dir);
                Equal(Path.GetFullPath(pdf), found, "pdf");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("build: a PDF with no time is found", () =>
        {
            var dir = Scratch();
            try
            {
                var pdf = Path.Combine(dir, "out.pdf");
                File.WriteAllText(pdf, "pdf");
                var found = BuildRunner.FindMadePdf("OK    report.md > out.pdf  (typst)", "report.md", dir);
                Equal(Path.GetFullPath(pdf), found, "pdf");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("build: a relative PDF in the project root is found", () =>
        {
            var dir = Scratch();
            try
            {
                var parts = Path.Combine(dir, "parts");
                Directory.CreateDirectory(parts);
                var pdf = Path.Combine(dir, "report.pdf");
                File.WriteAllText(pdf, "pdf");
                var found = BuildRunner.FindMadePdf("OK    ../report.md > report.pdf  in 1.2 s", "intro.md", parts, dir);
                Equal(Path.GetFullPath(pdf), found, "pdf");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("build: no OK line falls back to the source's own name", () =>
        {
            var dir = Scratch();
            try
            {
                var pdf = Path.Combine(dir, "intro.pdf");
                File.WriteAllText(pdf, "pdf");
                var found = BuildRunner.FindMadePdf("no build line", "intro.md", dir);
                Equal(Path.GetFullPath(pdf), found, "pdf");
            }
            finally { Directory.Delete(dir, true); }
        });

        Check("build: a PDF that is not there is not invented", () =>
        {
            var dir = Scratch();
            try { Equal(null, BuildRunner.FindMadePdf("no build line", "intro.md", dir), "pdf"); }
            finally { Directory.Delete(dir, true); }
        });

        Check("build: the studio does not build its PDF and picture tabs", () =>
        {
            True(!MainWindow.IsText("report.pdf"), "pdf");
            True(!MainWindow.IsText("drawing.PNG"), "png");
            True(MainWindow.IsText("report.md"), "markdown");
            True(MainWindow.IsText("data.txt"), "text");
        });

        Check("placement: a window off every screen is centred", () =>
        {
            var window = new Window();
            var placement = new WindowPlacement { Left = -20000, Top = -20000, Width = 900, Height = 700 };
            placement.ApplyTo(window);
            Equal(WindowStartupLocation.CenterScreen, window.WindowStartupLocation, "startup location");
        });

        Check("placement: a window on screen keeps its rectangle", () =>
        {
            var window = new Window();
            var placement = new WindowPlacement
            {
                Left = SystemParameters.WorkArea.Left + 20,
                Top = SystemParameters.WorkArea.Top + 20,
                Width = 800,
                Height = 600
            };
            placement.ApplyTo(window);
            Equal(WindowStartupLocation.Manual, window.WindowStartupLocation, "startup location");
            Near(SystemParameters.WorkArea.Left + 20, window.Left, "left");
            Near(SystemParameters.WorkArea.Top + 20, window.Top, "top");
            Near(800, window.Width, "width");
            Near(600, window.Height, "height");
        });

        Check("settings: the defaults allow a build and a server", () =>
        {
            var settings = new AppSettings();
            True(settings.BuildTimeoutSeconds >= 30, "build timeout");
            True(settings.ServerStartTimeoutSeconds >= 3, "server timeout");
            True(settings.SaveTimeoutSeconds >= 3, "save timeout");
            True(settings.BuildPaneHeight >= 120, "pane height");
        });

        Check("job: a child job is created and closed", () =>
        {
            using var job = new ChildJob();
            Equal(null, job.Warning, "warning");
        });

        output.WriteLine($"{passed} passed, {failed} failed.");
        return failed == 0 ? 0 : 1;
    }

    private static string Scratch()
    {
        var dir = Path.Combine(Path.GetTempPath(), "colophon-win-selftest-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        return dir;
    }

    private static void True(bool value, string what)
    {
        if (!value) throw new InvalidOperationException(what + " is not true");
    }

    private static void Equal<T>(T expected, T actual, string what)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
            throw new InvalidOperationException($"{what}: expected {Show(expected)}, got {Show(actual)}");
    }

    private static string Show<T>(T value) => value is null ? "null" : value.ToString() ?? "null";

    private static void Near(double expected, double actual, string what)
    {
        if (Math.Abs(expected - actual) > 0.5)
            throw new InvalidOperationException($"{what}: expected {expected}, got {actual}");
    }
}
