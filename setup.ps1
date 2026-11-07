# Setup Code AG to run with 'code ag' or 'codeag' from any terminal
$proj = "C:\Users\Darshan P L\Desktop\code AG"
$venv = "C:\Users\Darshan P L\Desktop\code AG\.venv\Scripts"

# 1. Add to User PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = $userPath -split ';' | Where-Object { $_ -ne '' -and $_ -ne $proj -and $_ -ne $venv }
$newPath = ($proj, $venv + $parts) -join ';'
[Environment]::SetEnvironmentVariable("Path", $newPath, "User")
Write-Host "[OK] Added to User PATH: $proj" -ForegroundColor Green

# 2. Add PowerShell function to $PROFILE so 'Code AG' works seamlessly in PowerShell
try {
    $profileDir = Split-Path $PROFILE -Parent
    if (!(Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir -Force | Out-Null }
    if (!(Test-Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force | Out-Null }
    
    $profileContent = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
    if ($profileContent -notmatch "function Code\b") {
        $funcDefinition = @"

# Code AG custom command launcher
function Code {
    param([Parameter(ValueFromRemainingArguments=`$true)]`$argsList)
    if (`$argsList.Count -gt 0 -and `$argsList[0] -match '^(ag|AG)$') {
        & '$venv\codeag.exe' `$argsList[1..(`$argsList.Count-1)]
    } else {
        if (Test-Path 'C:\Users\Darshan P L\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd') {
            & 'C:\Users\Darshan P L\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd' @argsList
        } else {
            & '$venv\codeag.exe' @argsList
        }
    }
}
function codeag { & '$venv\codeag.exe' @args }
function CodeAG { & '$venv\codeag.exe' @args }
"@
        Add-Content $PROFILE $funcDefinition
        Write-Host "[OK] Added PowerShell profile function to: $PROFILE" -ForegroundColor Green
    } else {
        Write-Host "[INFO] Profile function already registered in: $PROFILE" -ForegroundColor Cyan
    }
} catch {
    Write-Host "[NOTE] Profile update skipped: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "Please RESTART your terminal window, then type:" -ForegroundColor Yellow
Write-Host "  Code AG" -ForegroundColor Cyan
Write-Host "  codeag" -ForegroundColor Cyan

