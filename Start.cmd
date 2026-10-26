@echo off
cd /d "%~dp0"
if exist "python\python.exe" ("python\python.exe" run.py all) else (python run.py all)
pause
