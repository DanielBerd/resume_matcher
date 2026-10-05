; Inno Setup script for Resume Matcher (https://jrsoftware.org/isinfo.php).
;
; Build the app first:
;   dotnet publish src/ResumeMatcher.App -p:PublishProfile=win-x64
; then compile this with ISCC.exe to get Output/ResumeMatcherSetup.exe.

#define AppName    "Resume Matcher"
#define AppVersion "1.0.0"
#define AppExe     "ResumeMatcher.exe"
; Must match the id the app sets at startup, or Windows will not pin it correctly.
#define AppUserId  "DanielBerd.ResumeMatcher"

[Setup]
AppId={{7C3F1E2A-9B4D-4C6E-8A15-2D7F9E4B1C88}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Daniel
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=Output
OutputBaseFilename=ResumeMatcherSetup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user install by default: no admin prompt, and the app can write its own
; folders. Users who want it for everyone can still elevate.
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\src\ResumeMatcher.App\bin\publish\win-x64\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; AppUserModelID on the Start Menu shortcut is what makes "Pin to taskbar"
; attach to this app rather than to the bare executable.
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserId}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppUserId}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings are the user's; leave Documents\Resume Matcher alone on uninstall.
Type: filesandordirs; Name: "{userappdata}\ResumeMatcher"
