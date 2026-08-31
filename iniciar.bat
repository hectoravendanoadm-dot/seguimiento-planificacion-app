@echo off
setlocal
cd /d "%~dp0"

if not exist venv (
    echo ============================================
    echo   Primera vez: creando entorno e instalando
    echo   dependencias. Esto puede tardar un minuto...
    echo ============================================
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: no se encontro Python. Instalalo desde
        echo https://www.python.org/downloads/ y marca la
        echo casilla "Add python.exe to PATH" durante la instalacion.
        echo.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Iniciando Seguimiento y Planificacion...
echo (se abrira el navegador en unos segundos)
echo.
echo Para cerrar la app, cierra esta ventana o presiona Ctrl+C.
echo.

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5050"
python app.py

pause
