@echo off
rem Creates a Windows task that runs 3-run-now every day at 07:00 (or as soon as the PC is on).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute '%~dp0.venv\Scripts\python.exe' -Argument 'src\run_daily.py' -WorkingDirectory '%~dp0';" ^
  "$t = New-ScheduledTaskTrigger -Daily -At 07:00;" ^
  "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName 'FunFactsShorts' -Action $a -Trigger $t -Settings $s -Force | Out-Null;" ^
  "Write-Host 'Daily schedule is ON (07:00). To turn it off run 5-turn-off-daily-schedule.bat'"
pause
