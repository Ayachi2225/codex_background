@echo off
setlocal
set "HELPER=%~dp0scripts\codex_background.py"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 "%HELPER%" disable-autostart
) else (
  python "%HELPER%" disable-autostart
)

if errorlevel 1 goto :failed
echo Automatic loading is disabled. The current app will not restart.
timeout /t 2 /nobreak >nul
exit /b 0

:failed
echo Disabling automatic loading failed. Review the message above.
pause
exit /b 1
