@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Compilando Seguimiento y Planificacion
echo   como programa de escritorio (.exe)
echo ============================================
echo.

rem Se usa directamente el Python del venv de ESTA carpeta, sin "activarlo".
rem Asi funciona aunque el venv se haya creado o copiado desde otra ruta.
set "PY=%~dp0venv\Scripts\python.exe"

if not exist "%PY%" (
    echo No se encontro el entorno virtual "venv" en esta carpeta.
    echo Corre primero iniciar.bat al menos una vez para crearlo.
    echo.
    pause
    exit /b 1
)

echo Instalando/actualizando dependencias de compilacion...
"%PY%" -m pip install -r requirements.txt -q
if errorlevel 1 goto error_pip
"%PY%" -m pip install pyinstaller -q
if errorlevel 1 goto error_pip

echo.
echo Limpiando compilaciones anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SeguimientoPlanificacion.spec del /q SeguimientoPlanificacion.spec

echo.
echo Compilando (esto puede tardar 1-3 minutos)...
echo.

"%PY%" -m PyInstaller --noconfirm --onedir --windowed --name "SeguimientoPlanificacion" --icon "icon.ico" --add-data "templates;templates" --add-data "static;static" desktop_app.py
if errorlevel 1 goto error_build

echo.
echo ============================================
echo   Listo! El programa quedo en:
echo   dist\SeguimientoPlanificacion\SeguimientoPlanificacion.exe
echo ============================================
echo.
echo Siguiente paso: copia tu carpeta "data" completa
echo (Excel + documentos + diagramas) dentro de:
echo   dist\SeguimientoPlanificacion\
echo justo al lado del .exe.
echo.
pause
exit /b 0

:error_pip
echo.
echo ============================================
echo   ERROR: no se pudieron instalar las
echo   dependencias. Revisa el mensaje de arriba
echo   - puede ser la conexion o el proxy.
echo ============================================
pause
exit /b 1

:error_build
echo.
echo ============================================
echo   ERROR: la compilacion fallo. Revisa el
echo   mensaje de arriba.
echo ============================================
pause
exit /b 1
