# Ícono de acceso directo para el Escritorio

## Instalación (una sola vez)

1. Copia estos 3 archivos dentro de tu carpeta del proyecto (la misma donde está `iniciar.bat`):
   - `icon.ico`
   - `crear_acceso_directo.bat`
   - `crear_acceso_directo.ps1`

2. Haz doble clic en `crear_acceso_directo.bat`.

3. Listo — aparecerá un acceso directo llamado **"Seguimiento y Planificacion"** en tu
   Escritorio, con el ícono nuevo. Doble clic ahí en vez de entrar a la carpeta cada vez.

> Si Windows muestra un aviso de seguridad al ejecutar el `.bat`, es normal — dale
> "Más información" → "Ejecutar de todas formas" (o botón derecho → Abrir). Solo pasa la
> primera vez, ya que el archivo viene de fuera de tu equipo.

## ¿Qué hace exactamente?

`crear_acceso_directo.bat` corre un script de PowerShell (`crear_acceso_directo.ps1`) que:
- Crea un acceso directo (`.lnk`) en tu Escritorio
- Lo apunta a `iniciar.bat` (el launcher que ya tenías)
- Le asigna `icon.ico` como ícono
- Configura la carpeta de trabajo correcta para que la app encuentre sus archivos

No modifica nada de tu proyecto existente — solo agrega el acceso directo.

## Si quieres cambiar el ícono más adelante

Puedes reemplazar `icon.ico` por cualquier otro archivo `.ico` que prefieras y volver a
correr `crear_acceso_directo.bat` — se actualiza el acceso directo con el ícono nuevo.
