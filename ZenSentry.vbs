Set WshShell = CreateObject("WScript.Shell")
' Run pythonw.exe (windowless) pointing to zen_main.py
' Adjust path if pythonw is not in PATH or if using a venv
' Assuming standard environment
WshShell.Run "pythonw.exe c:\zen_sentry\zen_main.py", 0
Set WshShell = Nothing
