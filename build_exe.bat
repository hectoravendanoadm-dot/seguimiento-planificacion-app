@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   Compilando Seguimiento y Planificacion
echo   como programa de escritorio (.exe)
echo ============================================
echo.

if not exist venv (
    echo No se encontro el entorno virtual (venv).
    echo Corre primero iniciar.bat al menos una vez para crearlo.
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Instalando/actualizando dependencias de compilacion...
pip install -r requirements.txt -q
pip install pyinstaller -q

echo.
echo Limpiando compilaciones anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist SeguimientoPlanificacion.spec del /q SeguimientoPlanificacion.spec

echo.
echo Compilando (esto puede tardar 1-3 minutos)...
echo.

pyinstaller --onefile --windowed ^
  --name "SeguimientoPlanificacion" ^
  --icon "icon.ico" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  desktop_app.py

if errorlevel 1 (
    echo.
    echo ============================================
    echo   ERROR: la compilacion fallo. Revisa el
    echo   mensaje de arriba.
    echo ============================================
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Listo! El programa quedo en:
echo   dist\SeguimientoPlanificacion.exe
echo ============================================
echo.
echo Siguiente paso: crea la carpeta "data" junto a ese .exe
echo y copia ahi tu Seguimiento_y_planificacion.xlsx
echo.
pause
