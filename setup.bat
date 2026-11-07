@echo off
echo ========================================================
echo Setting up Code AG terminal commands...
echo ========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); $proj = 'C:\Users\Darshan P L\Desktop\code AG'; $venv = 'C:\Users\Darshan P L\Desktop\code AG\.venv\Scripts'; $parts = $userPath -split ';' | Where-Object { $_ -ne '' -and $_ -ne $proj -and $_ -ne $venv }; $newPath = ($proj, $venv + $parts) -join ';'; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); Write-Host 'Successfully configured PATH!' -ForegroundColor Green"
echo.
echo Setup Complete!
echo.
echo Please CLOSE and REOPEN your terminal window.
echo Then you can type:
echo   code ag   (opens Code AG)
echo   codeag    (opens Code AG)
echo.
pause

