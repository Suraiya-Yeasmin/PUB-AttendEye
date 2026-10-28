@echo off
rem Builds dist\PUB AttendEye\ and (if Inno Setup is installed) dist-installer\PUB-AttendEye-Setup-<version>.exe
rem Run from the project root on a Windows PC with Python 3.10-3.13:   packaging\build_windows.bat
setlocal
cd /d %~dp0\..
if not exist .build-venv ( python -m venv .build-venv || goto :fail )
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
pip install -r requirements.txt pyinstaller pillow || goto :fail
python scripts\download_models.py || goto :fail
python packaging\make_icon.py || goto :fail
pyinstaller packaging\attendeye.spec --noconfirm --distpath dist --workpath build || goto :fail

for /f "tokens=2 delims==" %%v in ('findstr /b "APP_VERSION" app\config.py') do set VER=%%~v
set VER=%VER: =%
set VER=%VER:"=%
set ISCC=
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%p set ISCC=%%~p
if defined ISCC (
  "%ISCC%" /DAppVersion=%VER% packaging\installer.iss || goto :fail
  echo.
  echo DONE. Installer: dist-installer\PUB-AttendEye-Setup-%VER%.exe
) else (
  echo.
  echo App folder built: dist\PUB AttendEye\PUB AttendEye.exe
  echo Install Inno Setup 6 ^(https://jrsoftware.org/isinfo.php^) and re-run to also produce the installer.
)
exit /b 0
:fail
echo BUILD FAILED
exit /b 1
