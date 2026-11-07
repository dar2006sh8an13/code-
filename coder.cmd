@echo off
setlocal
if /I "%~1"=="with" if /I "%~2"=="code" (
    shift
    shift
)
call "%~dp0code.cmd" %*

