@echo off
chcp 65001 >nul
title WorkBuddy Credential Fetcher
echo ========================================
echo   WorkBuddy Credential Fetcher
echo ========================================
echo.
echo Reading local WorkBuddy login state...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $c1=Join-Path $env:LOCALAPPDATA 'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info'; $c2=Join-Path $env:APPDATA 'CodeBuddyExtension\Data\Public\auth\workbuddy-desktop.info'; $f=@($c1,$c2) | Where-Object { Test-Path $_ } | Select-Object -First 1; if(-not $f){ Write-Host '[ERROR] Login state file not found. Make sure WorkBuddy is signed in.' -ForegroundColor Red; Write-Host '        Looked in:'; Write-Host ('          '+$c1); Write-Host ('          '+$c2); Write-Host ''; pause; exit 1 }; $d=Get-Content -Raw -Encoding UTF8 $f | ConvertFrom-Json; if(-not $d){ Write-Host '[ERROR] Login file is not valid JSON.' -ForegroundColor Red; pause; exit 1 }; $ph=$d.account.phoneNumber; $at=$d.auth.accessToken; $rt=$d.auth.refreshToken; $miss=@(); if(-not $ph){$miss+='account.phoneNumber'}; if(-not $at){$miss+='auth.accessToken'}; if(-not $rt){$miss+='auth.refreshToken'}; if($miss.Count -gt 0){ Write-Host ('[ERROR] Missing field(s): '+($miss -join ', ')) -ForegroundColor Red; Write-Host '        If you signed in with email instead of phone, the CI script' -ForegroundColor Yellow; Write-Host '        still expects phone:AT:RT format - use a phone-bound account.' -ForegroundColor Yellow; pause; exit 1 }; Set-Clipboard -Value ($ph+':'+$at+':'+$rt); $mask=''; if($ph.Length -ge 7){ $mask=$ph.Substring(0,3)+'****'+$ph.Substring($ph.Length-4) } else { $mask='***' }; Write-Host '[OK] Credential copied to clipboard (NOT printed here on purpose).' -ForegroundColor Green; Write-Host ('     phone        : '+$mask); Write-Host ('     accessToken  : '+$at.Length+' chars'); Write-Host ('     refreshToken : '+$rt.Length+' chars'); if($d.auth.refreshExpiresAt){ $ex=[DateTimeOffset]::FromUnixTimeMilliseconds([int64]$d.auth.refreshExpiresAt).LocalDateTime; $days=[math]::Floor(($ex-(Get-Date)).TotalDays); Write-Host ('     expires      : '+$ex.ToString('yyyy-MM-dd')+'  (in '+$days+' days)') -ForegroundColor Cyan }; Write-Host ''; Write-Host 'Next: paste into GitHub repo Secret  WORKBUDDY_REFRESH_TOKEN' -ForegroundColor Green; Write-Host '      Settings - Secrets and variables - Actions - New repository secret' ; Write-Host ''; pause"

echo.
