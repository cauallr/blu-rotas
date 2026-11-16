@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1" %*
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar. Leia a mensagem acima e o README.md.
  pause
)
