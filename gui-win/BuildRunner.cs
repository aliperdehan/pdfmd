using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace ColophonWin;

public sealed class BuildOutcome
{
    public int ExitCode { get; init; }
    public bool TimedOut { get; init; }
    public bool CouldNotStart { get; init; }
    public string Output { get; init; } = "";
    public string? PdfPath { get; init; }
    public double Seconds { get; init; }
    public string? Error { get; init; }
    public bool Ok => !TimedOut && !CouldNotStart && ExitCode == 0;
}

public static class BuildRunner
{
    public static async Task<BuildOutcome> RunAsync(PdfmdCommand command, string folder, string fileArgument, string projectRoot,
                                                    ChildJob job, int timeoutSeconds, Action<string> output,
                                                    CancellationToken cancellation)
    {
        var arguments = new[] { fileArgument };
        var start = PdfmdLocator.StartInfo(command, folder, arguments);
        var text = new StringBuilder();
        var gate = new object();
        var started = Stopwatch.StartNew();

        void Add(string line)
        {
            lock (gate) text.AppendLine(line);
            output(line);
        }

        using var process = new Process { StartInfo = start };
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) Add(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) Add(e.Data); };

        try
        {
            if (!process.Start())
                return new BuildOutcome { ExitCode = -1, CouldNotStart = true, Error = "pdfmd did not start." };
            job.Assign(process);
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
        }
        catch (Exception ex)
        {
            return new BuildOutcome { ExitCode = -1, CouldNotStart = true, Error = "pdfmd could not be started: " + ex.Message };
        }

        var timedOut = false;
        try
        {
            using var limit = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            limit.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));
            await process.WaitForExitAsync(limit.Token);
        }
        catch (OperationCanceledException)
        {
            timedOut = !cancellation.IsCancellationRequested;
            try
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
                process.WaitForExit(5000);
            }
            catch
            {
            }
        }

        process.WaitForExit();
        started.Stop();
        string all;
        lock (gate) all = text.ToString();
        var pdf = process.HasExited && process.ExitCode == 0
            ? FindMadePdf(all, fileArgument, folder, projectRoot)
            : null;
        return new BuildOutcome
        {
            ExitCode = process.HasExited ? process.ExitCode : -1,
            TimedOut = timedOut,
            Output = all,
            PdfPath = pdf,
            Seconds = started.Elapsed.TotalSeconds,
            Error = timedOut ? $"the build ran for more than {timeoutSeconds} s" : null
        };
    }

    public static string? FindMadePdf(string output, string sourceFile, string workingDirectory, string? projectRoot = null)
    {
        foreach (var raw in output.Split('\n'))
        {
            var line = raw.TrimEnd('\r');
            if (!line.StartsWith("OK", StringComparison.Ordinal)) continue;
            var at = line.IndexOf(" > ", StringComparison.Ordinal);
            if (at < 0) continue;
            var named = line[(at + 3)..].Trim();
            named = Regex.Replace(named, @"\s+in\s+\d[\d:.]*\s*s?\s*(\(.*\))?\s*$", "");
            named = Regex.Replace(named, @"\s+\([^)]*\)\s*$", "");
            if (named.Length == 0) continue;
            var found = Resolve(named, workingDirectory, projectRoot);
            if (found is not null) return found;
        }

        var source = Path.IsPathRooted(sourceFile) ? sourceFile : Path.Combine(workingDirectory, sourceFile);
        var same = Path.ChangeExtension(source, ".pdf");
        return File.Exists(same) ? Path.GetFullPath(same) : null;
    }

    private static string? Resolve(string named, string workingDirectory, string? projectRoot)
    {
        var candidates = new List<string>();
        if (Path.IsPathRooted(named)) candidates.Add(named);
        else
        {
            candidates.Add(Path.Combine(workingDirectory, named));
            if (projectRoot is not null) candidates.Add(Path.Combine(projectRoot, named));
        }
        foreach (var candidate in candidates)
        {
            var full = Path.GetFullPath(candidate);
            if (File.Exists(full)) return full;
        }
        return null;
    }
}
