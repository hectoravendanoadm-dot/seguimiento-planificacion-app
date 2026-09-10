"""
Punto de entrada para la version de escritorio (Nivel 3).

Corre el mismo backend Flask de siempre, pero en segundo plano, y lo muestra
en una ventana nativa de Windows (via pywebview) en lugar de una pestaña de
navegador. Este es el script que PyInstaller empaqueta como el .exe final -
app.py sigue siendo el mismo backend de siempre, sin tocarse para nada del
flujo normal (python app.py sigue funcionando igual que antes).
"""
import os
import threading
import time
import urllib.request

import webview

import app as backend

HOST = "127.0.0.1"
PORT = 5050
URL = f"http://{HOST}:{PORT}"


def _mostrar_error_nativo(mensaje):
    """Cuadro de dialogo nativo de Windows, sin depender de una consola."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, mensaje, "Seguimiento y Planificación", 0x10)
    except Exception:
        print(mensaje)


def _run_flask():
    backend.app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def _esperar_servidor(timeout=10):
    """Espera a que Flask responda antes de abrir la ventana, en vez de un
    time.sleep a ciegas — evita una ventana en blanco si el arranque demora."""
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    if not os.path.exists(backend.EXCEL_PATH):
        _mostrar_error_nativo(
            "No se encontró tu archivo Excel.\n\n"
            f"Cópialo dentro de la carpeta 'data' junto al programa, con el nombre:\n"
            f"Seguimiento_y_planificacion.xlsx\n\n"
            f"Ruta esperada:\n{backend.EXCEL_PATH}"
        )
        return

    hilo_servidor = threading.Thread(target=_run_flask, daemon=True)
    hilo_servidor.start()

    if not _esperar_servidor():
        _mostrar_error_nativo("La aplicación no pudo iniciar a tiempo. Intenta abrirla de nuevo.")
        return

    webview.create_window(
        "Seguimiento y Planificación",
        URL,
        width=1440,
        height=900,
        min_size=(1000, 650),
    )
    webview.start()


if __name__ == "__main__":
    main()
