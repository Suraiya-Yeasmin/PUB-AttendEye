# PUB AttendEye installer (per-user, no administrator rights needed). Started by "Install PUB AttendEye.vbs".
# Installs a private Python runtime + libraries + face models into %LOCALAPPDATA%\PUB-AttendEye and creates shortcuts.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$PythonVersion = '3.12.8'
$PythonUrl  = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$GetPipUrl  = 'https://bootstrap.pypa.io/get-pip.py'

$Pkg     = Split-Path -Parent $PSScriptRoot
$Home_   = Join-Path $env:LOCALAPPDATA 'PUB-AttendEye'
$AppDir  = Join-Path $Home_ 'app'
$RtDir   = Join-Path $Home_ 'runtime'
$PyDir   = Join-Path $RtDir 'python'
$Models  = Join-Path $Home_ 'models'
$LogDir  = Join-Path $Home_ 'logs'
$Tmp     = Join-Path $Home_ 'tmp'
$Ready   = Join-Path $Home_ '.ready'
$Log     = Join-Path $LogDir 'install.log'
foreach ($d in @($Home_, $LogDir, $Tmp)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

function Log($m) { Add-Content -Path $Log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }
function Pump { [System.Windows.Forms.Application]::DoEvents() }

# ---- progress window ---------------------------------------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Installing PUB AttendEye'
$form.StartPosition = 'CenterScreen'; $form.ClientSize = New-Object System.Drawing.Size(480, 150)
$form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false; $form.MinimizeBox = $true; $form.ControlBox = $false
$title = New-Object System.Windows.Forms.Label
$title.Text = 'Setting up PUB AttendEye'; $title.Font = New-Object System.Drawing.Font('Segoe UI', 13, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(20, 16); $title.Size = New-Object System.Drawing.Size(440, 30)
$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = 'Starting...'; $lbl.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$lbl.Location = New-Object System.Drawing.Point(20, 54); $lbl.Size = New-Object System.Drawing.Size(440, 24)
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Location = New-Object System.Drawing.Point(20, 84); $bar.Size = New-Object System.Drawing.Size(440, 22); $bar.Minimum = 0; $bar.Maximum = 100
$note = New-Object System.Windows.Forms.Label
$note.Text = 'First-time setup downloads about 150 MB and can take a few minutes. Please keep this window open.'
$note.Font = New-Object System.Drawing.Font('Segoe UI', 8.5); $note.ForeColor = [System.Drawing.Color]::DimGray
$note.Location = New-Object System.Drawing.Point(20, 114); $note.Size = New-Object System.Drawing.Size(440, 30)
$form.Controls.AddRange(@($title, $lbl, $bar, $note))
$form.Show(); Pump

function Step([int]$pct, [string]$text) { $bar.Value = [Math]::Min(100, $pct); $lbl.Text = $text; Log $text; Pump }
function Wait-Task($t) {
  while (-not $t.IsCompleted) { Pump; Start-Sleep -Milliseconds 80 }
  if ($t.IsFaulted) { throw $t.Exception.InnerException }
}
function Get-File([string]$url, [string]$dest) {
  Log "download $url"
  $wc = New-Object System.Net.WebClient
  try { Wait-Task ($wc.DownloadFileTaskAsync($url, $dest)) } finally { $wc.Dispose() }
}
function Invoke-Hidden([string]$exe, [string]$arguments, [string]$workDir) {
  $out = Join-Path $Tmp 'out.txt'; $err = Join-Path $Tmp 'err.txt'
  Log "run $exe $arguments"
  $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $workDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
  $null = $p.Handle
  while (-not $p.HasExited) { Pump; Start-Sleep -Milliseconds 120 }
  $p.WaitForExit()
  foreach ($f in @($out, $err)) { if (Test-Path $f) { Get-Content $f -ErrorAction SilentlyContinue | ForEach-Object { Add-Content $Log $_ } } }
  if ($p.ExitCode -ne 0) { throw "Command failed (exit code $($p.ExitCode)): $exe $arguments" }
}
function Quote([string]$s) { '"' + $s + '"' }

try {
  Log "=== install started; package=$Pkg ==="
  Step 3 'Closing any running copy of PUB AttendEye...'
  Get-Process -Name pythonw, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($RtDir, [StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { try { $_.Kill(); $_.WaitForExit(5000) | Out-Null } catch {} }

  Step 8 'Copying application files...'
  New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
  $null = & robocopy.exe $Pkg $AppDir /MIR /XD data models tests installer packaging .github .git __pycache__ /XF '*.pyc' 'Install PUB AttendEye.vbs' /NFL /NDL /NJH /NJS /NP
  if ($LASTEXITCODE -ge 8) { throw "Copying files failed (robocopy exit code $LASTEXITCODE)." }
  New-Item -ItemType Directory -Force -Path (Join-Path $Home_ 'installer') | Out-Null
  Copy-Item -Force (Join-Path $PSScriptRoot '*') (Join-Path $Home_ 'installer')

  $pyExe = Join-Path $PyDir 'python.exe'
  $pyOk = $false
  if (Test-Path $pyExe) { try { Invoke-Hidden $pyExe '-c "import fastapi, uvicorn, sqlalchemy, cv2, numpy, cryptography"' $AppDir; $pyOk = $true } catch { Log 'existing runtime incomplete; rebuilding' } }

  if (-not $pyOk) {
    Step 14 "Downloading Python $PythonVersion (private copy, not installed system-wide)..."
    if (Test-Path $RtDir) { Remove-Item -Recurse -Force $RtDir }
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
    $zip = Join-Path $Tmp 'python-embed.zip'
    Get-File $PythonUrl $zip
    Step 24 'Unpacking Python...'
    Expand-Archive -Path $zip -DestinationPath $PyDir -Force
    $pth = Get-ChildItem $PyDir -Filter 'python*._pth' | Select-Object -First 1
    if (-not $pth) { throw 'The Python package looks wrong (no ._pth file found).' }
    $zipName = (Get-ChildItem $PyDir -Filter 'python*.zip' | Select-Object -First 1).Name
    Set-Content -Path $pth.FullName -Encoding ASCII -Value @($zipName, '.', 'Lib\site-packages', '..\..\app', 'import site')

    Step 30 'Downloading the package installer (pip)...'
    $gp = Join-Path $Tmp 'get-pip.py'
    Get-File $GetPipUrl $gp
    Step 36 'Installing pip...'
    Invoke-Hidden $pyExe ((Quote $gp) + ' --no-warn-script-location --disable-pip-version-check') $AppDir

    Step 44 'Installing libraries (OpenCV, FastAPI, ...). This is the longest step...'
    $req = Join-Path $AppDir 'requirements-desktop.txt'
    Invoke-Hidden $pyExe ('-m pip install --no-warn-script-location --disable-pip-version-check -r ' + (Quote $req)) $AppDir
  }

  Step 78 'Downloading the face detection and recognition models (about 37 MB)...'
  $env:ATTENDEYE_MODEL_DIR = $Models
  Invoke-Hidden $pyExe (Quote (Join-Path $AppDir 'scripts\download_models.py')) $AppDir

  Step 90 'Checking the installation...'
  $env:ATTENDEYE_DATA_DIR = Join-Path $Home_ 'data'
  Invoke-Hidden $pyExe '-c "import cv2, fastapi, uvicorn, sqlalchemy, cryptography, numpy; import app.main"' $AppDir

  Step 95 'Creating shortcuts...'
  $launch = Join-Path $Home_ 'installer\launch.vbs'
  $icon = Join-Path $Home_ 'installer\icon.ico'
  $wsh = New-Object -ComObject WScript.Shell
  function New-Link($path, $target, $args_, $desc) {
    $l = $wsh.CreateShortcut($path); $l.TargetPath = $target; $l.Arguments = $args_; $l.WorkingDirectory = $Home_
    $l.IconLocation = $icon; $l.Description = $desc; $l.Save()
  }
  $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
  $startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PUB AttendEye'
  New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
  New-Link (Join-Path ([Environment]::GetFolderPath('Desktop')) 'PUB AttendEye.lnk') $wscript ('"' + $launch + '"') 'Open PUB AttendEye'
  New-Link (Join-Path $startMenu 'PUB AttendEye.lnk') $wscript ('"' + $launch + '"') 'Open PUB AttendEye'
  New-Link (Join-Path $startMenu 'Uninstall PUB AttendEye.lnk') $wscript ('"' + (Join-Path $Home_ 'installer\uninstall.vbs') + '"') 'Remove PUB AttendEye'

  Set-Content -Path $Ready -Value (Get-Date -Format o)
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
  Step 100 'Done.'
  Log '=== install finished OK ==='
  $form.Close()

  $r = [System.Windows.Forms.MessageBox]::Show("PUB AttendEye is installed.`n`nUse the 'PUB AttendEye' icon on your Desktop or Start menu to open it. The first time, you will be asked to create the administrator account.`n`nOpen it now?", 'PUB AttendEye', 'YesNo', 'Information')
  if ($r -eq 'Yes') { Start-Process -FilePath $wscript -ArgumentList ('"' + $launch + '"') }
}
catch {
  Log ("ERROR: " + $_.Exception.Message)
  try { $form.Close() } catch {}
  [System.Windows.Forms.MessageBox]::Show("The installation could not be completed.`n`n$($_.Exception.Message)`n`nCommon causes: no internet connection, or a firewall/proxy that blocks python.org, pypa.io or github.com.`n`nDetails were saved to:`n$Log", 'PUB AttendEye - installation failed', 'OK', 'Error') | Out-Null
  exit 1
}
