# Removes PUB AttendEye. Asks before deleting attendance data and face templates.
$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.Windows.Forms
$Home_ = Join-Path $env:LOCALAPPDATA 'PUB-AttendEye'
$RtDir = Join-Path $Home_ 'runtime'
$ask = [System.Windows.Forms.MessageBox]::Show("Remove PUB AttendEye from this computer?`n`nYour attendance data and enrolled face templates are kept unless you choose to delete them in the next question.", 'Uninstall PUB AttendEye', 'YesNo', 'Question')
if ($ask -ne 'Yes') { exit 0 }
$delData = [System.Windows.Forms.MessageBox]::Show("Also permanently delete ALL attendance data, student records and face templates?`n`nYes = delete everything (cannot be undone)`nNo = keep the data folder so a reinstall finds it again", 'Delete data?', 'YesNo', 'Warning')

Get-Process -Name pythonw, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($RtDir, [StringComparison]::OrdinalIgnoreCase) } |
  ForEach-Object { try { $_.Kill(); $_.WaitForExit(5000) | Out-Null } catch {} }
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath('Desktop')) 'PUB AttendEye.lnk') -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path ([Environment]::GetFolderPath('Programs')) 'PUB AttendEye') -ErrorAction SilentlyContinue
foreach ($d in 'app', 'runtime', 'models', 'logs', 'tmp') { Remove-Item -Recurse -Force (Join-Path $Home_ $d) -ErrorAction SilentlyContinue }
Remove-Item -Force (Join-Path $Home_ '.ready') -ErrorAction SilentlyContinue
if ($delData -eq 'Yes') { Remove-Item -Recurse -Force (Join-Path $Home_ 'data') -ErrorAction SilentlyContinue }
# This script lives in $Home_\installer; remove it last through a detached cmd so it can delete itself.
$left = if ($delData -eq 'Yes') { "rmdir /s /q `"$Home_`"" } else { "rmdir /s /q `"$Home_\installer`"" }
Start-Process -WindowStyle Hidden -FilePath cmd.exe -ArgumentList "/c ping -n 3 127.0.0.1 >nul & $left"
[System.Windows.Forms.MessageBox]::Show($(if ($delData -eq 'Yes') { 'PUB AttendEye and all its data were removed.' } else { "PUB AttendEye was removed. Your data was kept in:`n$Home_\data" }), 'PUB AttendEye', 'OK', 'Information') | Out-Null
