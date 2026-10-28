; Inno Setup script -> PUB-AttendEye-Setup.exe  (build with:  iscc /DAppVersion=1.0.0 packaging\installer.iss)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "PUB AttendEye"
#define AppExe  "PUB AttendEye.exe"

[Setup]
AppId={{6B1D7E52-3C0A-4F57-9A55-7C2E5E1B0A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PUB AttendEye
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=PUB-AttendEye-Setup-{#AppVersion}
SetupIconFile=attendeye.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\PUB AttendEye\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Student face templates and attendance records live in %LOCALAPPDATA%\PUB AttendEye. Never delete them silently.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\PUB AttendEye');
    if DirExists(DataDir) then
      if MsgBox('Also delete all attendance records, student data and face templates stored on this computer?' + #13#10 +
                '(' + DataDir + ')' + #13#10#13#10 +
                'Choose No to keep them (recommended if you may reinstall).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
