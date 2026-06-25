' DOLG public launcher: visible console window, no silent pythonw/tray mode.
' Double-click this file to open a terminal and run start_public.bat.
Option Explicit

Dim sh, fso, root, bat, cmdExe, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\start_public.bat"

If Not fso.FileExists(bat) Then
    MsgBox "start_public.bat not found:" & vbCrLf & bat, 16, "DOLG launcher"
    WScript.Quit 1
End If

sh.CurrentDirectory = root
cmdExe = sh.ExpandEnvironmentStrings("%ComSpec%")
cmd = Chr(34) & cmdExe & Chr(34) & " /k " & Chr(34) & Chr(34) & bat & Chr(34) & Chr(34)

' 1 = normal visible window, False = do not wait.
sh.Run cmd, 1, False
