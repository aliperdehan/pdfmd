using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace ColophonWin;

public sealed record ServeInfo(string Url, int Port, string Token);

public sealed class ServeSession : IDisposable
{
    private readonly StringBuilder _error = new();
    private readonly object _gate = new();
    private bool _disposed;

    public Process Process { get; }
    public ServeInfo Info { get; }
    public string Folder { get; }
    public string CommandLine { get; }
    public event Action<int>? Stopped;

    private ServeSession(Process process, ServeInfo info, string folder, string commandLine)
    {
        Process = process;
        Info = info;
        Folder = folder;
        CommandLine = commandLine;
        process.EnableRaisingEvents = true;
        process.Exited += (_, _) =>
        {
            if (!_disposed) Stopped?.Invoke(SafeExitCode());
        };
    }

    public string ErrorText
    {
        get { lock (_gate) return _error.ToString(); }
    }

    public static async Task<ServeSession> StartAsync(string folder, ChildJob job, int timeoutSeconds, CancellationToken cancellation)
    {
        var command = PdfmdLocator.Find();
        var arguments = new[] { "--serve", folder };
        var start = PdfmdLocator.StartInfo(command, folder, arguments);
        start.Environment["PDFMD_SERVE_PARENT"] = Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var process = new Process { StartInfo = start };
        var started = new TaskCompletionSource<ServeInfo>(TaskCreationOptions.RunContinuationsAsynchronously);
        var session = new ServeSession(process, new ServeInfo("", 0, ""), folder,
                                       PdfmdLocator.Display(command, folder, arguments));

        process.OutputDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            var line = e.Data.Trim();
            if (!line.StartsWith('{')) return;
            try
            {
                using var document = JsonDocument.Parse(line);
                var root = document.RootElement;
                var url = root.GetProperty("url").GetString();
                var port = root.GetProperty("port").GetInt32();
                var token = root.GetProperty("token").GetString();
                if (!string.IsNullOrEmpty(url) && !string.IsNullOrEmpty(token))
                    started.TrySetResult(new ServeInfo(url, port, token));
            }
            catch (JsonException)
            {
            }
        };
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            lock (session._gate)
            {
                if (session._error.Length < 20000) session._error.AppendLine(e.Data);
            }
        };

        try
        {
            if (!process.Start()) throw new InvalidOperationException("pdfmd did not start.");
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException("pdfmd could not be started: " + ex.Message, ex);
        }

        job.Assign(process);
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        process.Exited += (_, _) =>
        {
            if (!started.Task.IsCompleted)
                started.TrySetException(new InvalidOperationException("pdfmd --serve stopped before it printed a URL"));
        };

        try
        {
            var info = await started.Task.WaitAsync(TimeSpan.FromSeconds(timeoutSeconds), cancellation);
            var running = new ServeSession(process, info, folder, session.CommandLine);
            session._disposed = true;
            return running;
        }
        catch (Exception ex) when (ex is TimeoutException or OperationCanceledException or InvalidOperationException)
        {
            Kill(process);
            await Task.Delay(100);
            throw new InvalidOperationException(
                $"pdfmd --serve did not print a URL within {timeoutSeconds} s" + Detail(session.ErrorText), ex);
        }
    }

    private static string Detail(string error) =>
        string.IsNullOrWhiteSpace(error) ? "." : ":\n" + error.Trim();

    private int SafeExitCode()
    {
        try { return Process.ExitCode; } catch { return -1; }
    }

    private static void Kill(Process process)
    {
        try
        {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
            process.WaitForExit(3000);
        }
        catch
        {
        }
    }

    public void Dispose()
    {
        if (_disposed && Process.HasExited) return;
        _disposed = true;
        Kill(Process);
        Process.Dispose();
    }
}
