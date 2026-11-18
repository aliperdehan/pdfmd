using System.IO;
using System.Windows;

namespace ColophonWin;

public partial class App : Application
{
    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        if (e.Args.Contains("--selftest"))
        {
            ConsoleSupport.Attach();
            Shutdown(SelfTest.Run(Console.Out));
            return;
        }

        var target = CommandLineTarget.Parse(e.Args);
        if (target.Error is not null)
        {
            MessageBox.Show(target.Error, "Colophon", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(2);
            return;
        }

        var window = new MainWindow(target);
        MainWindow = window;
        window.Show();
        await window.StartAsync();
    }
}

public sealed record CommandLineTarget(string? Folder, string? File, string? Error)
{
    public static CommandLineTarget Parse(string[] args)
    {
        var words = args.Where(a => !a.StartsWith("--", StringComparison.Ordinal)).ToArray();
        if (words.Length == 0) return new(null, null, null);
        if (words.Length > 1) return new(null, null, "Give one file or folder.");

        string path;
        try { path = Path.GetFullPath(words[0]); }
        catch (Exception ex) { return new(null, null, "That path cannot be read: " + ex.Message); }

        if (Directory.Exists(path)) return new(path, null, null);
        if (System.IO.File.Exists(path))
        {
            var folder = Path.GetDirectoryName(path);
            return folder is null
                ? new(null, null, "That file has no folder.")
                : new(folder, Path.GetFileName(path), null);
        }

        var parent = Path.GetDirectoryName(path);
        if (parent is not null && Directory.Exists(parent)) return new(parent, Path.GetFileName(path), null);
        return new(null, null, "No such file or folder: " + path);
    }
}

internal static class ConsoleSupport
{
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern bool AttachConsole(int processId);

    public static void Attach()
    {
        AttachConsole(-1);
    }
}
