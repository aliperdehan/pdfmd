using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using Microsoft.Win32;

namespace ColophonWin;

public static class Theme
{
    public static bool IsDark()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            return key?.GetValue("AppsUseLightTheme") is int light && light == 0;
        }
        catch
        {
            return false;
        }
    }

    public static void Apply(bool dark)
    {
        var r = Application.Current.Resources;
        r["WindowBrush"] = Brush(dark ? "#202020" : "#F3F3F3");
        r["PanelBrush"] = Brush(dark ? "#2B2B2B" : "#FAFAFA");
        r["ForegroundBrush"] = Brush(dark ? "#F0F0F0" : "#1B1B1B");
        r["MutedBrush"] = Brush(dark ? "#A0A0A0" : "#666666");
        r["BorderBrush"] = Brush(dark ? "#3C3C3C" : "#D6D6D6");
        r["ButtonBrush"] = Brush(dark ? "#333333" : "#FFFFFF");
        r["ButtonHoverBrush"] = Brush(dark ? "#404040" : "#EDEDED");
        r["TextBackgroundBrush"] = Brush(dark ? "#1B1B1B" : "#FFFFFF");
        r["AccentBrush"] = Brush(dark ? "#6FA8F0" : "#2F6FBA");
    }

    public static void ApplyTitleBar(Window window, bool dark)
    {
        var hwnd = new WindowInteropHelper(window).Handle;
        if (hwnd == IntPtr.Zero) return;
        var value = dark ? 1 : 0;
        if (DwmSetWindowAttribute(hwnd, 20, ref value, sizeof(int)) != 0)
            DwmSetWindowAttribute(hwnd, 19, ref value, sizeof(int));
    }

    private static SolidColorBrush Brush(string colour)
    {
        var b = new SolidColorBrush((Color)ColorConverter.ConvertFromString(colour));
        b.Freeze();
        return b;
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
}

public sealed class ThemeWatcher : IDisposable
{
    public event Action<bool>? Changed;

    public ThemeWatcher()
    {
        SystemEvents.UserPreferenceChanged += OnPreferenceChanged;
    }

    private void OnPreferenceChanged(object sender, UserPreferenceChangedEventArgs e)
    {
        var dark = Theme.IsDark();
        Application.Current?.Dispatcher.BeginInvoke(() => Changed?.Invoke(dark));
    }

    public void Dispose()
    {
        SystemEvents.UserPreferenceChanged -= OnPreferenceChanged;
    }
}
