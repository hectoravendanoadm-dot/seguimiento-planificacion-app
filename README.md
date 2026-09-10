# Seguimiento y Planificación — App local

Aplicativo local que reemplaza el uso manual del Excel "Seguimiento y planificación" por una
interfaz web sencilla. **Lee y escribe directamente sobre el archivo `.xlsx`** — no usa base
de datos por ahora, así que el Excel sigue siendo tu única fuente de verdad. Cada vez que
guardas un cambio en la app, se actualiza el archivo en `data/`.

## 1. Requisitos

- Python 3.9 o superior instalado.
- El archivo Excel a trabajar (mismo formato que "Seguimiento y planificación.xlsx",
  con hojas `Tareas` y `Listas`).

## 2. Instalación (una sola vez)

Abre una terminal en esta carpeta y ejecuta:

```bash
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configurar tu archivo Excel

Coloca tu Excel dentro de la carpeta `data/` con el nombre exacto:

```
data/Seguimiento_y_planificacion.xlsx
```

Ya viene una copia de tu archivo actual ahí, lista para usar. Si más adelante quieres apuntar
a otro archivo (por ejemplo, uno sincronizado desde OneDrive con la app de escritorio de
OneDrive, que se ve como una carpeta local normal), reemplaza este archivo o edita la
constante `EXCEL_PATH` en `app.py` para que apunte a esa ruta.

> ⚠️ **Importante:** si el Excel está abierto en Microsoft Excel al mismo tiempo que usas la
> app, Windows puede bloquear el archivo e impedir que la app guarde cambios. Ciérralo en
> Excel mientras trabajas desde el aplicativo.

## 4. Ejecutar la app

**Opción rápida (recomendada): doble clic en el launcher**

Dentro de la carpeta del proyecto encontrarás dos archivos, uno por sistema operativo — usa
el que corresponda al tuyo:

- **Windows**: `iniciar.bat`
- **Mac**: `iniciar_mac.command`

Haz doble clic sobre el que te corresponda y listo:
- La primera vez, crea el entorno virtual e instala todo automáticamente (tarda ~1 minuto).
- Las siguientes veces, arranca la app directamente.
- Abre el navegador solo, en `http://127.0.0.1:5050`.
- Para cerrar la app, simplemente cierra la ventana que se abrió (o presiona Ctrl+C).

> **En Mac, la primera vez que lo abras:** macOS puede bloquear el archivo por venir de
> internet ("no se puede abrir porque proviene de un desarrollador no identificado"). Si
> pasa, haz clic derecho (o Control+clic) sobre `iniciar_mac.command` → **Abrir** → confirma
> en el cuadro que aparece. Solo hace falta la primera vez.

**Opción manual (línea de comandos):**

```bash
python app.py
```

Verás un mensaje con la URL. Abre tu navegador en:

```
http://127.0.0.1:5050
```

Para detener la app, vuelve a la terminal y presiona `Ctrl + C`.

## 5. Qué puedes hacer

- **Vista Tabla**: todas las tareas en formato lista, con filtros por proyecto, estado,
  prioridad, responsable y búsqueda de texto libre.
- **Vista Kanban**: tareas agrupadas por estado, para ver el flujo de trabajo de un vistazo.
- **Vista Planificación**: réplica interactiva del Gantt semanal (mes → semana), agrupado por
  proyecto. Al crear o editar tareas, proyectos, meses y semanas se abren cuadros de diálogo
  con el mismo diseño que el resto de la app (ya no son los cuadros simples del navegador).
  Los cambios se guardan directo en la hoja "Planificacion" del Excel.
  - **Marcar/editar una semana (o varias a la vez)**: al hacer clic en una celda se abre un
    panel con campo de texto y una paleta de 10 colores. Para marcar varias semanas seguidas
    de una sola vez (por ejemplo, todo un sprint de desarrollo), tienes dos formas:
    - **Arrastrar el mouse** desde la primera semana hasta la última dentro de la misma fila.
    - **Clic en la primera + Shift y clic en la última** (como en Excel), útil si prefieres
      no arrastrar o el mouse es impreciso.
    En ambos casos se resaltan las semanas seleccionadas y, al soltar, se abre el mismo panel
    aplicando el texto y color elegido a todas juntas en un solo guardado.
  - **Reordenar tareas**: cada tarea tiene dos flechitas (▲/▼) junto a su nombre para
    moverla arriba o abajo dentro de su mismo proyecto — útil cuando te acuerdas de una
    tarea que debía ir antes de otras. Se mueve toda la fila junto con sus semanas
    marcadas. No se puede mover una tarea fuera de los límites de su proyecto (las flechas
    se desactivan cuando ya está al principio o al final).
- **Módulo "Equipo y Proyectos"**: pantalla dedicada para gestionar las listas de proyectos y
  responsables que alimentan los desplegables de Tabla y Planificación — sin tocar el Excel
  directamente. Como los equipos y proyectos cambian con el tiempo, aquí puedes:
  - **Agregar** un proyecto o responsable nuevo.
  - **Renombrar** uno existente — con la opción de actualizar automáticamente (en cascada)
    todas las tareas y secciones de Planificación que ya usaban ese nombre, para no perder
    el histórico cuando cambia un rol o se renombra un proyecto.
  - **Eliminar** uno de la lista — si está en uso, te avisa cuántas tareas lo referencian
    antes de confirmar (las tareas existentes mantienen el texto, solo deja de aparecer
    como opción para tareas nuevas).
  - Cada elemento muestra cuántas tareas lo están usando actualmente.
- **Módulo "Pasos a Prod"**: lleva el registro de cada paso a producción de los desarrollos,
  con las mismas columnas que ya tenías en el Excel (Fecha, Tema, Producto, OTC, Ticket
  Jira). Funciona igual que la vista Tabla: clic en cualquier fila para editarla, botón
  "+ Nuevo paso a prod" para agregar uno. Los enlaces de OTC y Ticket Jira se muestran como
  links clickeables que abren en una pestaña nueva.
  - **+ Nuevo proyecto**: agrega una nueva sección/proyecto al final de la planificación.
  - **+ Agregar tarea** (al final de cada proyecto): agrega una fila de tarea dentro de ese
    proyecto específico.
  - **+ Agregar mes**: extiende la línea de tiempo agregando un mes nuevo con la cantidad de
    semanas que definas — ya no está limitado a octubre, puedes seguir agregando meses
    indefinidamente.
  - **Eliminar**: cada tarea, proyecto y mes tiene un botón "×" para borrarlo si te
    equivocaste (por ejemplo, si agregaste un mes con el número de semanas incorrecto).
    Borrar un proyecto elimina también todas sus tareas — te pedirá confirmación.
  - **Editar nombre**: haz clic directo sobre el nombre de una tarea para renombrarla o
    editar su nota (por ejemplo, cambiar "Desarrollo Front" por "Desarrollo Front + Back")
    sin perder las semanas ya marcadas. Los proyectos tienen un botón ✎ para renombrarlos
    igual, conservando todas sus tareas.
  - **Colapsar proyectos**: haz clic en el nombre de un proyecto (▾/▸) para contraer o
    expandir sus tareas. Al colapsarlo, la fila muestra las semanas pintadas con el color
    real que ya tenías en el Excel para ese proyecto (igual que se ve en el archivo
    original) — y puedes seguir haciendo clic sobre esas celdas para extender o ajustar el
    rango de duración del proyecto.
  - **Editar o eliminar una semana puntual**: cada columna de semana tiene su propio botón
    "×" (borra solo esa semana, sin tocar el resto del mes) y su etiqueta es clickeable para
    corregir el texto o el mes al que pertenece.
- **Crear / editar / eliminar tareas** desde la interfaz — se guarda directo en el Excel.
- **Descargar Excel**: botón en la esquina superior derecha para bajar una copia del archivo
  actualizado.

Cada vez que guardas un cambio, la app crea automáticamente un respaldo
(`data/Seguimiento_y_planificacion.backup.xlsx`) con el estado anterior, por si necesitas
deshacer algo manualmente.

## 6. Próximos pasos (roadmap conversado)

- **Sincronización con OneDrive**: se puede conectar vía Microsoft Graph API para leer/escribir
  el archivo directamente en la nube, sin depender de la app de escritorio de OneDrive.
- **Migración a base de datos local (SQLite)**: cuando el volumen de tareas crezca o varias
  personas necesiten editar a la vez, conviene migrar de Excel a una base de datos real.
  El backend ya está en Flask/Python, por lo que ese cambio no implica rehacer la interfaz,
  solo la capa de acceso a datos (`app.py`).
- **Multiusuario**: hoy la app asume un solo usuario editando a la vez (como el Excel). Migrar
  a base de datos habilita edición concurrente sin pisarse cambios.

## 7. Respaldo en Supabase (fuera de la red local)

El botón **"☁ Respaldar en Supabase"** de la barra superior sube una copia del Excel
(con marca de tiempo, más una copia siempre llamada `Seguimiento_y_planificacion_ultimo.xlsx`)
y de todo lo que haya en `data/documentos/` y `data/diagramas/` a un bucket de
Supabase Storage. Es solo un respaldo manual — la app sigue funcionando 100% con el
Excel local, y no depende de internet salvo cuando presionas ese botón.

**Configuración (una sola vez):**

1. Crea un proyecto gratis en [supabase.com](https://supabase.com).
2. En el proyecto, ve a **Storage** y crea un bucket (por ejemplo `respaldos`).
3. En **Project Settings → API**, copia la **Project URL** y la **service_role key**
   (no la `anon/public` — la `service_role` tiene permisos de escritura y por eso
   vive solo en este archivo local, nunca en el navegador ni en el código).
4. Crea (o edita) el archivo `.env` en la raíz del proyecto (mismo nivel que `app.py`)
   con este contenido:

   ```
   SUPABASE_URL=https://TU-PROYECTO.supabase.co
   SUPABASE_SERVICE_KEY=tu-service-role-key
   SUPABASE_BUCKET=respaldos
   ```

El archivo `.env` está en `.gitignore` — nunca se sube a ningún repositorio ni se
comparte al enviar el proyecto.

**Importante:** la `service_role key` da acceso total al proyecto de Supabase. Si en algún
momento crees que quedó expuesta (por ejemplo, pegada en un chat), regénerala desde
**Project Settings → API → Generate new service_role key**.

## 8. Convertirla en un programa de escritorio (.exe, sin consola)

Si prefieres no depender de `iniciar.bat` ni de una pestaña de navegador, puedes compilar
la app en un único archivo `.exe` que se abre en su propia ventana — se ve y se siente como
cualquier otro programa instalado en Windows.

**Instalación (una sola vez):**

1. Asegúrate de haber corrido `iniciar.bat` al menos una vez antes (crea el `venv`).
2. Haz doble clic en `build_exe.bat`. Instala PyInstaller y compila — tarda 1-3 minutos.
3. Cuando termine, el programa queda en `dist\SeguimientoPlanificacion.exe`.
4. Crea una carpeta `data` justo al lado de ese `.exe`, y copia ahí tu
   `Seguimiento_y_planificacion.xlsx` (igual que en la versión normal).
5. Doble clic en `SeguimientoPlanificacion.exe` — abre una ventana propia, sin consola negra
   y sin navegador. Puedes crearle un acceso directo en el Escritorio (clic derecho →
   Crear acceso directo) o anclarlo a la barra de tareas.

**Cómo funciona por dentro:** sigue siendo el mismo backend Flask de siempre (`app.py`)
corriendo en segundo plano — solo que en vez de abrir Chrome/Edge, se muestra dentro de una
ventana nativa de Windows (vía `pywebview`), y PyInstaller empaqueta Python + todas las
dependencias dentro del `.exe`, así que **no necesitas tener Python instalado** para
correrlo (sí lo necesitas para compilarlo).

**Notas importantes:**
- Tus datos (`data/`) siempre quedan junto al `.exe` real, no se pierden entre ejecuciones.
- Si cambias el código (`app.py`, `templates/`, `static/`), tienes que volver a correr
  `build_exe.bat` para que el `.exe` refleje los cambios — no se actualiza solo.
- La ventana usa **WebView2** (el motor de Microsoft Edge moderno). Windows 11 ya lo trae
  instalado; en Windows 10 casi siempre también, pero si la ventana aparece en blanco,
  descarga el "Microsoft Edge WebView2 Runtime" (gratis, instalador chico) desde la página
  oficial de Microsoft.
- El `.exe` no se sube a GitHub (`dist/`, `build/` y `*.spec` están en `.gitignore`) — cada
  quien lo compila localmente con `build_exe.bat`.

## Estructura del proyecto

```
seguimiento-app/
├── app.py                # Backend Flask (lee/escribe el Excel, sube a Supabase)
├── desktop_app.py         # Punto de entrada para la version de escritorio (.exe)
├── build_exe.bat          # Compila desktop_app.py a un .exe con PyInstaller
├── requirements.txt
├── .env                  # Credenciales de Supabase (no se versiona)
├── .gitignore
├── data/
│   ├── Seguimiento_y_planificacion.xlsx   # Tu archivo de trabajo
│   ├── documentos/       # Archivos subidos en Documentación → Documentos
│   └── diagramas/        # Archivos subidos en Documentación → Repositorio de diagramas
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```
