@echo off
setlocal
set "HELPER=%~dp0scripts\codex_background.py"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 "%HELPER%" doctor
  if errorlevel 1 goto :failed
  py -3 "%HELPER%" start
) else (
  python "%HELPER%" doctor
  if errorlevel 1 goto :failed
  python "%HELPER%" start
)

if errorlevel 1 goto :failed
echo Background helper started. ChatGPT/Codex will restart.
timeout /t 2 /nobreak >nul
exit /b 0

:failed
echo codex_background failed. Review the message above.
pause
exit /b 1
