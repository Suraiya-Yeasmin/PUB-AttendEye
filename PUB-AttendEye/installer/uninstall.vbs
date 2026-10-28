Option Explicit
Dim sh, home
Set sh = CreateObject("WScript.Shell")
home = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\PUB-AttendEye"
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & home & "\installer\uninstall.ps1""", 0, False
