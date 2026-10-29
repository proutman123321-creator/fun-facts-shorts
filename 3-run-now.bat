@echo off
rem Makes today's videos and sends them to Zernio (draft or schedule, see config.json).
cd /d "%~dp0"
".venv\Scripts\python.exe" src\run_daily.py
pause
