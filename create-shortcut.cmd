@echo off
rem Creates a desktop shortcut for quick local launch.
chcp 65001 >nul
set "SCRIPT=%~dp0start.cmd"
set "LINK=%USERPROFILE%\Desktop\Самопомощь.lnk"

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath='%SCRIPT%';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.Description='Запуск сервиса Самопомощь';" ^
  "$s.Save()"

if exist "%LINK%" (
    echo.
    echo   Shortcut created on Desktop: Самопомощь
    echo.
) else (
    echo   Failed to create shortcut.
)
pause
