@echo off
rem Lists your TikTok / Instagram accounts connected in Zernio, with their IDs for config.json.
cd /d "%~dp0"
".venv\Scripts\python.exe" src\publish.py accounts
pause
