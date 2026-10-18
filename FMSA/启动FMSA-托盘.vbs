Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "pythonw.exe """ & fso.BuildPath(fso.BuildPath(dir, "tools"), "fmsa_tray.py") & """", 0, False
