@echo off
title Selfhelp - tunnel
cd /d "%~dp0"

echo.
echo  Public tunnel for http://127.0.0.1:8000
echo  ========================================
echo.
echo  Checking local server...
curl -s -o NUL -w "  local server: HTTP %%{http_code}\n" --max-time 5 http://127.0.0.1:8000/
echo.
echo  Opening tunnel. Look for a line like:
echo    https://xxxxx.app.lhr.life tunneled with tls termination
echo  Copy that https:// link and open it without VPN.
echo  Keep this window open. Stop with Ctrl+C.
echo.

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o ServerAliveInterval=30 -R 80:localhost:8000 nokey@localhost.run

echo.
echo  Tunnel closed.
pause
