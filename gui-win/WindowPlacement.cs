using System.IO;
using System.Text.Json;
using System.Windows;

namespace ColophonWin;

public static class AppPaths
{
    public static string DataDir
    {
        get
        {
            var given = Environment.GetEnvironmentVariable("COLOPHON_DATA_DIR");
            var dir = string.IsNullOrWhiteSpace(given)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Colophon")
                : given;
            Directory.CreateDirectory(dir);
            return dir;
        }
    }

    public static string WebViewDataDir
    {
        get
        {
            var dir = Path.Combine(DataDir, "WebView2");
            Directory.CreateDirectory(dir);
            return dir;
        }
    }

    public static string WindowFile => Path.Combine(DataDir, "window.json");
    public static string SettingsFile => Path.Combine(DataDir, "settings.json");
}

public sealed class WindowPlacement
{
    public double Left { get; set; }
    public double Top { get; set; }
    public double Width { get; set; }
    public double Height { get; set; }
    public bool Maximized { get; set; }

    public static WindowPlacement? Load()
    {
        try
        {
            if (!File.Exists(AppPaths.WindowFile)) return null;
            var placement = JsonSerializer.Deserialize<WindowPlacement>(File.ReadAllText(AppPaths.WindowFile));
            return placement is { Width: >= 400, Height: >= 300 } ? placement : null;
        }
        catch
        {
            return null;
        }
    }

    public void ApplyTo(Window window)
    {
        var left = Math.Max(Left, SystemParameters.VirtualScreenLeft);
        var top = Math.Max(Top, SystemParameters.VirtualScreenTop);
        var right = Math.Min(Left + Width, SystemParameters.VirtualScreenLeft + SystemParameters.VirtualScreenWidth);
        var bottom = Math.Min(Top + Height, SystemParameters.VirtualScreenTop + SystemParameters.VirtualScreenHeight);
        if (right - left < 200 || bottom - top < 150)
        {
            window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
            window.Width = Math.Min(Width, SystemParameters.WorkArea.Width);
            window.Height = Math.Min(Height, SystemParameters.WorkArea.Height);
            return;
        }
        window.Left = left;
        window.Top = top;
        window.Width = Width;
        window.Height = Height;
        if (Maximized) window.WindowState = WindowState.Maximized;
    }

    public static void Save(Window window)
    {
        var bounds = window.WindowState == WindowState.Normal
            ? new Rect(window.Left, window.Top, window.Width, window.Height)
            : window.RestoreBounds;
        var placement = new WindowPlacement
        {
            Left = bounds.Left,
            Top = bounds.Top,
            Width = bounds.Width,
            Height = bounds.Height,
            Maximized = window.WindowState == WindowState.Maximized
        };
        try { File.WriteAllText(AppPaths.WindowFile, JsonSerializer.Serialize(placement)); }
        catch { }
    }
}

public sealed class AppSettings
{
    public int BuildTimeoutSeconds { get; set; } = 600;
    public int ServerStartTimeoutSeconds { get; set; } = 20;
    public int SaveTimeoutSeconds { get; set; } = 15;
    public int BuildPaneHeight { get; set; } = 260;

    public static AppSettings Load()
    {
        try
        {
            if (!File.Exists(AppPaths.SettingsFile)) return new AppSettings();
            var s = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(AppPaths.SettingsFile));
            return s ?? new AppSettings();
        }
        catch
        {
            return new AppSettings();
        }
    }
}
