<#
Screenshot Spike 2.0 running in a REAL Windows terminal window, screen by screen.

    powershell -ExecutionPolicy Bypass -File scripts\windows\terminal_screenshots.ps1
    powershell -ExecutionPolicy Bypass -File scripts\windows\terminal_screenshots.ps1 -LoadSeconds 40

scripts/visual_audit.py shows what the app draws; this shows how THIS machine's
terminal draws it (font, box-drawing and block glyphs, colours, the console host).
It opens the app in Windows Terminal (or the classic console if Windows Terminal is
missing), types the same keys a person would (1-6, Esc, the comma for Settings,
/ for the palette, ? for help, q to quit) and saves one PNG of the window per
screen to outputs\visual_audit\terminal\. It reads nothing and changes nothing:
every key it sends only navigates.

Written on a Mac for the lab box and NOT yet run on Windows (2026-09-27): if a step
misbehaves (window not found, keys landing in the wrong window, timing), fix this
script as part of the audit and say what you changed.
#>
param(
    [string]$Out = "outputs\visual_audit\terminal",
    [int]$LoadSeconds = 30,        # controller load + the splash leaving on its own
    [int]$Width = 110,
    [int]$Height = 36
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SpikeWin {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[void][SpikeWin]::SetProcessDPIAware()        # real pixels on scaled displays

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$outDir = Join-Path $repo $Out
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$title = "SpikeAudit"

$before = @(Get-Process -Name WindowsTerminal, conhost, cmd -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Id })
if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    $wtArgs = "--title $title --suppressApplicationTitle --size $Width,$Height -d `"$repo`" " +
              "cmd /c uv run python SpikeInterface_Menu.py"
    Start-Process wt.exe -ArgumentList $wtArgs
    $host_name = "WindowsTerminal"
} else {
    Start-Process cmd.exe -ArgumentList "/c title $title && mode con: cols=$Width lines=$Height && cd /d `"$repo`" && uv run python SpikeInterface_Menu.py"
    $host_name = "cmd"
}

function Find-Window {
    for ($i = 0; $i -lt 60; $i++) {
        $p = Get-Process -ErrorAction SilentlyContinue |
             Where-Object { $_.MainWindowTitle -like "*$title*" -and $_.MainWindowHandle -ne 0 } |
             Select-Object -First 1
        if ($p) { return $p.MainWindowHandle }
        Start-Sleep -Milliseconds 500
    }
    throw "could not find the '$title' window ($host_name) - is it open?"
}

function Shot([string]$name) {
    $h = Find-Window
    [void][SpikeWin]::ShowWindow($h, 9)
    [void][SpikeWin]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 300
    $r = New-Object SpikeWin+RECT
    [void][SpikeWin]::GetWindowRect($h, [ref]$r)
    $w = $r.Right - $r.Left; $hgt = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $hgt
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
    $file = Join-Path $outDir ("{0:D2}_{1}.png" -f $script:n, $name)
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Write-Host "saved $file"
    $script:n++
}

function Press([string]$keys, [double]$wait = 1.5) {
    $h = Find-Window
    [void][SpikeWin]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait($keys)
    Start-Sleep -Milliseconds ([int]($wait * 1000))
}

$script:n = 0
Start-Sleep -Seconds 4
Shot "loading_or_splash"
Start-Sleep -Seconds $LoadSeconds
Shot "home"
foreach ($s in @(@("1", "1_data", 1.5), @("2", "2_probe", 1.5), @("3", "3_sort", 1.5),
                 @("4", "4_judge", 6), @("5", "5_apply", 1.5), @("6", "6_share", 1.5))) {
    Press $s[0] $s[2]
    Shot $s[1]
}
Press "{ESC}" 1
Press "," 1.5;    Shot "settings";  Press "{ESC}" 1
Press "/phy" 1.5; Shot "palette";   Press "{ESC}" 1
Press "?" 1.5;    Shot "help";      Press "{ESC}" 1
Press "3" 1; Press "r" 2; Shot "runs"; Press "{ESC}" 1
Press "{ESC}" 1
Press "q" 2
Write-Host "done: $script:n screenshots in $outDir"
