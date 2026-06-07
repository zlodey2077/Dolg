' DOLG — запуск трей-лаунчера БЕЗ консольного окна (двойной клик).
' Поднимает иконку в системном трее; сервер стартует и открывает браузер сам.
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw  = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then pyw = "pythonw.exe"
sh.CurrentDirectory = root
' 0 = окно скрыто, False = не ждать завершения
sh.Run """" & pyw & """ """ & root & "\dolg_tray.py""", 0, False
