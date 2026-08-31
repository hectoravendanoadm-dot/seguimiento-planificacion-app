#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "============================================"
    echo "  Primera vez: creando entorno e instalando"
    echo "  dependencias. Esto puede tardar un minuto..."
    echo "============================================"
    if ! command -v python3 &> /dev/null; then
        echo ""
        echo "ERROR: no se encontró Python 3. Instálalo desde"
        echo "https://www.python.org/downloads/ y vuelve a intentar."
        echo ""
        read -p "Presiona Enter para cerrar..."
        exit 1
    fi
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo ""
echo "Iniciando Seguimiento y Planificacion..."
echo "(se abrirá el navegador en unos segundos)"
echo ""
echo "Para cerrar la app, cierra esta ventana o presiona Ctrl+C."
echo ""

( sleep 2 && open http://127.0.0.1:5050 ) &
python3 app.py

read -p "Presiona Enter para cerrar..."
