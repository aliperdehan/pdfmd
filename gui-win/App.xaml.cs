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

        var window = new MainWindow();
        MainWindow = window;
        window.Show();
        await window.StartAsync();
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
