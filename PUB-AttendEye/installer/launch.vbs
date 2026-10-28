' Opens PUB AttendEye (starts the local server in the background and shows the app window).
Option Explicit
Dim sh, fso, home, py, app
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
home = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\PUB-AttendEye"
py = home & "\runtime\python\pythonw.exe"
app = home & "\app"
If Not fso.FileExists(home & "\.ready") Or Not fso.FileExists(py) Then
  MsgBox "PUB AttendEye is not installed (or the installation was interrupted)." & vbCrLf & _
         "Please run ""Install PUB AttendEye"" again.", vbExclamation, "PUB AttendEye"
  WScript.Quit 1
End If
sh.Environment("PROCESS")("ATTENDEYE_DATA_DIR") = home & "\data"
sh.Environment("PROCESS")("ATTENDEYE_MODEL_DIR") = home & "\models"
sh.CurrentDirectory = app
sh.Run """" & py & """ """ & app & "\desktop.py""", 0, False
