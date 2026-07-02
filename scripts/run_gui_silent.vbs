Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
If Not fso.FileExists(root & "\pdfcompare_gui.py") Then
    root = fso.GetParentFolderName(root)
End If

pythonw = root & "\.venv\Scripts\pythonw.exe"
script = root & "\pdfcompare_gui.py"

If fso.FileExists(pythonw) Then
    shell.Run """" & pythonw & """ """ & script & """", 0, False
Else
    shell.Run "pyw -3 """ & script & """", 0, False
End If
