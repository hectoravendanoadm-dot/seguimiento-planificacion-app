@echo off
cd /d "%~dp0"
echo Creando acceso directo en el Escritorio...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0crear_acceso_directo.ps1"
