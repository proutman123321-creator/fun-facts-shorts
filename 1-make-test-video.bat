@echo off
rem Makes the next videos (one per post time of each enabled language) in the "output" folder. Sends nothing.
cd /d "%~dp0"
".venv\Scripts\python.exe" src\run_daily.py --no-publish
pause
