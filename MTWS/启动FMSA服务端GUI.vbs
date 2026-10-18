Dim WshShell, scriptDir, cmd
Set WshShell = CreateObject("WScript.Shell")
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
cmd = "pythonw """ & scriptDir & "server_gui.py"""
' 第三个参数 0 = 完全隐藏窗口，False = 不等待进程结束
WshShell.Run cmd, 0, False
