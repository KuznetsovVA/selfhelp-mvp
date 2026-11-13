@echo off
chcp 65001 >nul
title Selfhelp - autostart
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
    goto :run
)
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
    goto :run
)

echo Python not found. Install Python 3.12 from python.org
pause
exit /b 1

:run
"%PY%" autostart.py %*
pause
