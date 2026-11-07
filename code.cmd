@echo off
setlocal
if /I "%~1"=="vscode" (
    shift
    if exist "C:\Users\Darshan P L\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd" (
        "C:\Users\Darshan P L\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd" %*
        goto :eof
    )
)
if /I "%~1"=="ag" (
    shift
)
"%~dp0.venv\Scripts\codeag.exe" %*


