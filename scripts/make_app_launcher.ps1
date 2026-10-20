# Desktop shortcut that opens the app through scripts/hide_mouse_in_app.ahk.
# It carries the installed app's taskbar id, so once pinned, the app windows
# group under it. Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make_app_launcher.ps1
param(
    [string]$Ahk = "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe",
    [string]$AppId = "Chrome._crx_gmcbhmkeojidgcp.UserData.Profile1"
)

$ErrorActionPreference = "Stop"
$scripts = $PSScriptRoot
# The file is read as the ANSI code page, so the Korean name is spelled in code points.
$name = "$([char]0xBB38)$([char]0xC7A5) $([char]0xC77D)$([char]0xAE30)"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "$name.lnk"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class CShellLink {}

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
    void GetIDList(out IntPtr p);
    void SetIDList(IntPtr p);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetHotkey(out short h);
    void SetHotkey(short h);
    void GetShowCmd(out int c);
    void SetShowCmd(int c);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r);
    void Resolve(IntPtr h, uint f);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct AsrPropertyKey { public Guid fmtid; public uint pid; }

[StructLayout(LayoutKind.Explicit)]
public struct AsrPropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
interface IPropertyStore {
    void GetCount(out uint c);
    void GetAt(uint i, out AsrPropertyKey k);
    void GetValue(ref AsrPropertyKey k, out AsrPropVariant v);
    void SetValue(ref AsrPropertyKey k, ref AsrPropVariant v);
    void Commit();
}

public static class AsrLauncherLink {
    public static void Make(string lnk, string target, string args, string dir, string icon, string appId) {
        var link = (IShellLinkW)new CShellLink();
        link.SetPath(target);
        link.SetArguments(args);
        link.SetWorkingDirectory(dir);
        link.SetIconLocation(icon, 0);
        var store = (IPropertyStore)link;
        // PKEY_AppUserModel_ID
        var key = new AsrPropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
        var v = new AsrPropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };
        try {
            store.SetValue(ref key, ref v);
            store.Commit();
        } finally {
            Marshal.FreeCoTaskMem(v.p);
        }
        ((IPersistFile)link).Save(lnk, true);
    }
}
"@

$script = Join-Path $scripts "hide_mouse_in_app.ahk"
$icon = Join-Path $scripts "app_icon.ico"
[AsrLauncherLink]::Make($lnk, $Ahk, "`"$script`"", $scripts, $icon, $AppId)
Write-Output "made $lnk"
