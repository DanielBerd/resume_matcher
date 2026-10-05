using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;

namespace ResumeMatcher.App;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        // Escape hatch used when capturing both variants for documentation;
        // unset in normal use, where the window follows the Windows app mode.
        if (Environment.GetEnvironmentVariable("RM_FORCE_THEME") is { Length: > 0 } forced)
            RequestedThemeVariant = forced.Equals("Dark", StringComparison.OrdinalIgnoreCase)
                ? Avalonia.Styling.ThemeVariant.Dark
                : Avalonia.Styling.ThemeVariant.Light;

        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
            desktop.MainWindow = new MainWindow();

        base.OnFrameworkInitializationCompleted();
    }
}
