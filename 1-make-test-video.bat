@echo off
rem Makes one English and one French video in the "output" folder. Sends nothing.
cd /d "%~dp0"
".venv\Scripts\python.exe" src\run_daily.py --no-publish
pause
