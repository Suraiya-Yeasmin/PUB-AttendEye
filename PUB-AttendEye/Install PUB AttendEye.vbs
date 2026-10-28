' Double-click this file to install PUB AttendEye. No terminal or commands needed.
Option Explicit
Dim fso, sh, here, ps1
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = here & "\installer\install.ps1"
If Not fso.FileExists(ps1) Then
  MsgBox "The installer files were not found next to this file." & vbCrLf & vbCrLf & _
         "If you opened this from inside the .zip, close it, right-click the .zip, choose ""Extract All..."", " & _
         "and then double-click ""Install PUB AttendEye"" in the extracted folder.", vbExclamation, "PUB AttendEye"
  WScript.Quit 1
End If
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """", 0, False
