@echo off
title Selfhelp - server
cd /d "%~dp0"

echo.
echo  Starting Selfhelp server...
echo.

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

echo  Python not found. Install Python 3.12 from python.org
pause
exit /b 1

:run
echo  Server: http://127.0.0.1:8000
echo  Keep this window open.
echo.
"%PY%" server.py
pause
