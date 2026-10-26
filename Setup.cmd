@echo off
cd /d "%~dp0"
if exist "python\python.exe" ("python\python.exe" setup.py) else (python setup.py)
pause
