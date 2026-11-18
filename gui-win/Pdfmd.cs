using System.Diagnostics;
using System.IO;

namespace ColophonWin;

public sealed record PdfmdCommand(string FileName, IReadOnlyList<string> Prefix, string Display);

public static class PdfmdLocator
{
    public static PdfmdCommand Find()
    {
        var given = Environment.GetEnvironmentVariable("COLOPHON_PDFMD");
        if (!string.IsNullOrWhiteSpace(given))
        {
            var path = given.Trim().Trim('"');
            if (!File.Exists(path)) throw new FileNotFoundException("COLOPHON_PDFMD names no file: " + path);
            return Command(path, "COLOPHON_PDFMD");
        }

        var names = new[] { "pdfmd.exe", "pdfmd.cmd", "pdfmd.bat" };
        foreach (var folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(folder)) continue;
            foreach (var name in names)
            {
                var candidate = Path.Combine(folder.Trim().Trim('"'), name);
                if (File.Exists(candidate)) return Command(candidate, "PATH");
            }
        }

        throw new FileNotFoundException("pdfmd was not found on PATH. Install it (pip install -e . in the pdfmd clone), " +
                                        "or set COLOPHON_PDFMD to its executable.");
    }

    internal static PdfmdCommand Command(string path, string source)
    {
        var full = Path.GetFullPath(path);
        var extension = Path.GetExtension(full).ToLowerInvariant();
        if (extension is ".cmd" or ".bat")
        {
            var shell = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe";
            return new PdfmdCommand(shell, new[] { "/c", full }, $"{full} ({source})");
        }
        return new PdfmdCommand(full, Array.Empty<string>(), $"{full} ({source})");
    }

    public static ProcessStartInfo StartInfo(PdfmdCommand command, string workingDirectory, params string[] arguments)
    {
        var info = new ProcessStartInfo
        {
            FileName = command.FileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = new System.Text.UTF8Encoding(false),
            StandardErrorEncoding = new System.Text.UTF8Encoding(false)
        };
        foreach (var prefix in command.Prefix) info.ArgumentList.Add(prefix);
        foreach (var argument in arguments) info.ArgumentList.Add(argument);
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        return info;
    }

    public static string Display(PdfmdCommand command, string workingDirectory, IEnumerable<string> arguments)
    {
        var words = new List<string> { command.FileName };
        words.AddRange(command.Prefix);
        words.AddRange(arguments);
        return string.Join(" ", words.Select(Quote));
    }

    public static string Quote(string word) =>
        word.Length > 0 && !word.Any(char.IsWhiteSpace) && !word.Contains('"') ? word : "\"" + word.Replace("\"", "\\\"") + "\"";
}
