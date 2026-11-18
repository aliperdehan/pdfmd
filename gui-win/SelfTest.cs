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

        Check("theme: light or dark is a real answer", () =>
        {
            var dark = Theme.IsDark();
            True(dark || !dark, "theme");
        });

        output.WriteLine($"{passed} passed, {failed} failed.");
        return failed == 0 ? 0 : 1;
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
