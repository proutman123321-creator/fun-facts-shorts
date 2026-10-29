@echo off
powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'FunFactsShorts' -Confirm:$false; Write-Host 'Daily schedule is OFF.'"
pause
