# Spoty - masaustu kisayolunu olusturur/duzeltir ve gorev cubugu kimligini (AppUserModelID) yazar.
#
# NEDEN GEREKLI:
#   Uygulama Python ile calisir. Windows, bir pencerenin gorev cubugundaki kimligini
#   AppUserModelID'den belirler; ayarlanmamissa calisan .exe'den turetir. Bu yuzden
#   uygulama "Python" olarak gorunur ve sabitlenen (pin) kisayolla eslesmez.
#   Cozum iki parcali:
#     1) Uygulama kendi kimligini bildirir  -> spoty/webmain.py: _set_windows_app_id()
#     2) Kisayol AYNI kimligi tasir         -> bu script
#   Ikisi ayni olmazsa Windows yine eslestiremez.
#
# KULLANIM (proje kokunden):
#   powershell -ExecutionPolicy Bypass -File .\tools\fix_shortcut.ps1
#
# SONRASINDA: gorev cubugundaki ESKI sabitlemeyi kaldir, kisayolu calistir,
# calisan ikona sag tikla -> yeniden sabitle. Windows eski kimligi onbellege alir.

$ErrorActionPreference = 'Stop'

$AppId    = 'Ulger.Spoty'   # spoty/webmain.py icindeki APP_ID ile AYNI olmali
$Root     = Split-Path -Parent $PSScriptRoot
$Exe      = Join-Path $Root '.venv\Scripts\spoty.exe'
$IconFile = Join-Path $Root 'spoty.ico'
$Lnk      = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Spoty.lnk'

if (-not (Test-Path -LiteralPath $Exe)) {
  Write-Host "spoty.exe yok. Once paketi kur:" -ForegroundColor Yellow
  Write-Host "  .\.venv\Scripts\python.exe -m pip install -e ." -ForegroundColor Yellow
  exit 1
}

# --- 1) Kisayolu olustur/guncelle ---
$sh = New-Object -ComObject WScript.Shell
$l  = $sh.CreateShortcut($Lnk)
$l.TargetPath       = $Exe
$l.Arguments        = ''
$l.WorkingDirectory = $Root
$l.Description      = 'Spoty - kisisel muzik uygulamasi'
if (Test-Path -LiteralPath $IconFile) { $l.IconLocation = "$IconFile,0" }
$l.Save()

# --- 2) Kisayola AppUserModelID yaz (IShellLink + IPropertyStore) ---
# .NET'te hazir sarmalayici yok; COM arayuzleri elle tanimlanir.
if (-not ('LnkAumid' -as [type])) {
  Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class LnkAumid
{
    [StructLayout(LayoutKind.Sequential)]
    public struct PropertyKey { public Guid fmtid; public uint pid; }

    [StructLayout(LayoutKind.Sequential)]
    public struct PropVariant { public ushort vt; public ushort r1, r2, r3; public IntPtr p; public IntPtr p2; }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder n, int c);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string n);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder d, int c);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string d);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder a, int c);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
        void GetHotkey(out ushort h);
        void SetHotkey(ushort h);
        void GetShowCmd(out int c);
        void SetShowCmd(int c);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder i, int c, out int idx);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string i, int idx);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string p, uint r);
        void Resolve(IntPtr hwnd, uint fl);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string p);
    }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile {
        void GetClassID(out Guid c);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string f, [MarshalAs(UnmanagedType.Bool)] bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
    }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint c);
        void GetAt(uint i, out PropertyKey k);
        void GetValue(ref PropertyKey k, out PropVariant v);
        void SetValue(ref PropertyKey k, ref PropVariant v);
        void Commit();
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class ShellLink { }

    // Not: InitPropVariantFromString bir DLL girisi DEGIL (propvarutil.h icinde inline),
    // bu yuzden PROPVARIANT elle doldurulur: vt = VT_LPWSTR (31) + COM bellegine kopya.
    const ushort VT_LPWSTR = 31;

    [DllImport("ole32.dll")]
    static extern int PropVariantClear(ref PropVariant pv);

    // System.AppUserModel.ID
    static PropertyKey Key()
    {
        PropertyKey k = new PropertyKey();
        k.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
        k.pid = 5;
        return k;
    }

    public static void Set(string lnkPath, string appId)
    {
        IShellLinkW link = (IShellLinkW)new ShellLink();
        IPersistFile file = (IPersistFile)link;
        file.Load(lnkPath, 2);   // STGM_READWRITE

        IPropertyStore store = (IPropertyStore)link;
        PropertyKey key = Key();

        PropVariant pv = new PropVariant();
        pv.vt = VT_LPWSTR;
        pv.p = Marshal.StringToCoTaskMemUni(appId);
        store.SetValue(ref key, ref pv);
        store.Commit();
        PropVariantClear(ref pv);   // COM bellegini serbest birakir

        file.Save(lnkPath, true);
    }

    public static string Get(string lnkPath)
    {
        IShellLinkW link = (IShellLinkW)new ShellLink();
        ((IPersistFile)link).Load(lnkPath, 0);   // STGM_READ
        IPropertyStore store = (IPropertyStore)link;
        PropertyKey key = Key();
        PropVariant pv;
        store.GetValue(ref key, out pv);
        if (pv.vt == 31 && pv.p != IntPtr.Zero) { return Marshal.PtrToStringUni(pv.p); }
        return "(yok)";
    }
}
'@
}

[LnkAumid]::Set($Lnk, $AppId)

# --- 3) Dogrula ---
$check = $sh.CreateShortcut($Lnk)
Write-Host ""
Write-Host "Kisayol guncellendi: $Lnk"
Write-Host "  hedef      : $($check.TargetPath)"
Write-Host "  klasor     : $($check.WorkingDirectory)"
Write-Host "  ikon       : $($check.IconLocation)"
Write-Host "  AppUserModelID: $([LnkAumid]::Get($Lnk))   (beklenen: $AppId)"
Write-Host ""
Write-Host "SIRADAKI ADIM: gorev cubugundaki eski sabitlemeyi kaldir," -ForegroundColor Cyan
Write-Host "kisayolu calistir, calisan ikona sag tikla -> gorev cubugua sabitle." -ForegroundColor Cyan
