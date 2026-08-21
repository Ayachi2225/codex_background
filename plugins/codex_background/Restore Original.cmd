@echo off
setlocal
set "HELPER=%~dp0scripts\codex_background.py"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 "%HELPER%" restore
) else (
  python "%HELPER%" restore
)

if errorlevel 1 goto :failed
echo Original appearance restore scheduled. ChatGPT/Codex will restart.
timeout /t 2 /nobreak >nul
exit /b 0

:failed
echo codex_background restore failed. Review the message above.
pause
exit /b 1
