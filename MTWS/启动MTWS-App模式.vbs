Dim fso, sh, dir, launcher, logf, py, msg
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("Wscript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(dir, "app_launcher.py")
logf = fso.BuildPath(dir, "app_launcher_error.log")
py = ""
On Error Resume Next
Dim r
r = sh.RegRead("HKLM\SOFTWARE\Python\PythonCore\3.12\InstallPath\ExecutablePath")
If Err.Number = 0 And r <> "" Then py = r
Err.Clear
If py = "" Then
  Dim exec, out
  Set exec = sh.Exec("cmd /c where pythonw.exe")
  out = Trim(exec.StdOut.ReadAll())
  If out <> "" Then py = Split(out, vbCrLf)(0)
End If
Dim ts
Set ts = fso.OpenTextFile(logf, 8, True)
ts.WriteLine "=== " & Now & " ==="
ts.WriteLine "dir=" & dir
ts.WriteLine "launcher=" & launcher & " exists=" & fso.FileExists(launcher)
ts.WriteLine "py=" & py
ts.Close
If py = "" Then
  MsgBox "找不到 pythonw.exe，请先安装 Python 3.12+ 并勾选 PATH", 16, "MTWS"
Else
  sh.Run """" & py & """ """ & launcher & """", 0, False
End If
