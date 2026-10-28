# Building the Windows installer

The installer must be built on Windows (PyInstaller cannot cross-compile). Two ways:

## A. GitHub Actions (no Windows PC needed)
1. Push this project to a **private** GitHub repository (`data/` is git-ignored; never commit it).
2. Actions tab > **Build Windows installer** > Run workflow (or push a tag like `v1.0.0`).
3. Download the `PUB-AttendEye-Setup` artifact: `PUB-AttendEye-Setup-1.0.0.exe`. The job runs the tests and starts the built app to confirm the face models load before it packages.

## B. On a Windows PC
Install Python 3.10-3.13 and (optional, for the installer) Inno Setup 6, then:

    packaging\build_windows.bat

Output: `dist\PUB AttendEye\PUB AttendEye.exe` (portable folder) and `dist-installer\PUB-AttendEye-Setup-<version>.exe`.

## Notes
- The face models (~39 MB) are downloaded at build time and bundled, so the installed app works offline.
- Windows SmartScreen may warn "unknown publisher" because the installer is unsigned. Click *More info > Run anyway*. A code-signing certificate removes this.
- Bump `APP_VERSION` in `app/config.py` for each release.
