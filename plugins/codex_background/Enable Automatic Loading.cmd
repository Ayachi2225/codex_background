@echo off
setlocal
set "HELPER=%~dp0scripts\codex_background.py"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 "%HELPER%" enable-autostart
) else (
  python "%HELPER%" enable-autostart
)

if errorlevel 1 goto :failed
echo Automatic loading is enabled for the current and future sign-in sessions.
timeout /t 3 /nobreak >nul
exit /b 0

:failed
echo Enabling automatic loading failed. Review the message above.
pause
exit /b 1
