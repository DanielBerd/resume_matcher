# Creates the "Resume Matcher" shortcuts: one next to ResumeMatcher.bat and one
# in the Start Menu. Run by ResumeMatcher.bat on first launch.
#
# Both carry the app icon (a .bat cannot) and start the launcher's console
# minimized, so nothing flashes. They are also stamped with the same
# AppUserModelID the window declares (see gui.py). That is what lets Windows
# pin the app to the taskbar: "Pin to taskbar" on a running window looks for a
# Start Menu shortcut with a matching id and pins that; without one it pins
# pythonw.exe itself, which shows the Python icon and launches nothing.
# WScript.Shell cannot write that property, hence the shell COM interfaces.
param([Parameter(Mandatory = $true)][string]$Root)

$ErrorActionPreference = "Stop"
$AppId = "DanielBerd.ResumeMatcher"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace ResumeMatcher {
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  class ShellLink {}

  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
  interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int cch, IntPtr fd, uint flags);
    void GetIDList(out IntPtr pidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetHotkey(out short k);
    void SetHotkey(short k);
    void GetShowCmd(out int c);
    void SetShowCmd(int c);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int cch, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint reserved);
    void Resolve(IntPtr hwnd, uint flags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
  }

  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  struct PropertyKey { public Guid fmtid; public uint pid; public PropertyKey(Guid g, uint p) { fmtid = g; pid = p; } }

  [StructLayout(LayoutKind.Explicit)]
  struct PropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }

  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
  interface IPropertyStore {
    void GetCount(out uint c);
    void GetAt(uint i, out PropertyKey k);
    void GetValue(ref PropertyKey k, out PropVariant v);
    void SetValue(ref PropertyKey k, ref PropVariant v);
    void Commit();
  }

  public static class Shortcut {
    // PKEY_AppUserModel_ID
    static readonly Guid AppUserModel = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
    const int SW_SHOWMINNOACTIVE = 7;
    const ushort VT_LPWSTR = 31;

    public static void Create(string path, string target, string workDir, string icon, string description, string appId) {
      var link = (IShellLinkW)new ShellLink();
      link.SetPath(target);
      link.SetWorkingDirectory(workDir);
      link.SetIconLocation(icon, 0);
      link.SetDescription(description);
      link.SetShowCmd(SW_SHOWMINNOACTIVE);

      var store = (IPropertyStore)link;
      var key = new PropertyKey(AppUserModel, 5);
      var value = new PropVariant { vt = VT_LPWSTR, p = Marshal.StringToCoTaskMemUni(appId) };
      try { store.SetValue(ref key, ref value); store.Commit(); }
      finally { Marshal.FreeCoTaskMem(value.p); }

      ((IPersistFile)link).Save(path, true);
    }
  }
}
"@

$root = (Resolve-Path $Root).Path.TrimEnd('\')
$startMenu = [Environment]::GetFolderPath('Programs')
foreach ($lnk in @("$root\Resume Matcher.lnk", (Join-Path $startMenu 'Resume Matcher.lnk'))) {
    [ResumeMatcher.Shortcut]::Create(
        $lnk, "$root\ResumeMatcher.bat", $root, "$root\app\resume_matcher\icon.ico", "Resume Matcher", $AppId)
}
