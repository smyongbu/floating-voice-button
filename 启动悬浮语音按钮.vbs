Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
preferred = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe"
If fso.FileExists(preferred) Then
    runner = preferred
Else
    runner = "pythonw.exe"
End If
shell.Run """" & runner & """ """ & folder & "\app.py""", 0, False
