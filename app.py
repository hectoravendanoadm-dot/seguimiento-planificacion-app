"""
Seguimiento y Planificación - App local
Lee y escribe directamente sobre el archivo Excel (hoja "Tareas").
"""
import os
import re
import csv
import io
import json
import shutil
import urllib.request
import urllib.error
from copy import copy
from datetime import datetime, date
from flask import Flask, jsonify, request, send_file, render_template
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXCEL_PATH = os.path.join(DATA_DIR, "Seguimiento_y_planificacion.xlsx")
BACKUP_PATH = os.path.join(DATA_DIR, "Seguimiento_y_planificacion.backup.xlsx")
DOCS_DIR = os.path.join(DATA_DIR, "documentos")
DIAGRAMS_DIR = os.path.join(DATA_DIR, "diagramas")


def _load_env_file():
    """Carga variables desde un archivo .env local, sin depender de python-dotenv."""
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_env_file()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "respaldos")

TAREAS_SHEET = "Tareas"
LISTAS_SHEET = "Listas"
PROYECTOS_SHEET = "Proyectos"
PROYECTOS_COLUMNS = ["Nombre", "Fecha Inicio", "Fecha Fin", "Color", "Mostrar en Roadmap"]
PROYECTOS_PALETTE = ["2F5496", "0C8599", "C2410C", "7C3AED", "15803D", "B91C1C", "0E7490", "A16207", "4338CA", "BE185D"]
PASOS_PROD_SHEET = "Pasos a Prod"
PASOS_PROD_COLUMNS = ["Fecha", "Tema", "Producto", "OTC", "Ticket Jira"]
PLANIFICACION_SHEET = "Planificacion"
PLANIFICACION_FIRST_WEEK_COL = 3
PLANIFICACION_SECTION_NAMES = {"Comanda (Catering Jumbo)", "Robustecimiento", "Zippedi"}
PLANIFICACION_THEME_COLORS = {
    4: "#4472C4", 5: "#ED7D31", 6: "#A5A5A5",
    7: "#FFC000", 8: "#5B9BD5", 9: "#70AD47",
}
PLANIFICACION_DEFAULT_COLOR = "#F2A93B"

COLUMNS = [
    "ID", "Proyecto", "Tarea", "Subtarea", "Responsable", "Estado",
    "Prioridad", "% Avance", "Fecha Inicio", "Fecha Fin",
    "Horas Estimadas", "Horas Reales", "Notas", "Clave", "Log", "Orden Roadmap",
]

INCIDENCIAS_SHEET = "Incidencias"
INCIDENCIAS_COLUMNS = [
    "Fecha de reporte", "Cantidad", "Producto", "Título", "Tipo de incidencia",
    "Descripción", "Severidad", "Prioridad", "Estado", "Responsable (seguimiento)", "Responsable (desarrollo)",
    "Ticket Jira", "Fecha de resolución", "Solución aplicada", "Log",
]
INCIDENCIAS_DATE_FIELDS = ("Fecha de reporte", "Fecha de resolución")
INCIDENCIA_ESTADOS = ["En revisión", "En desarrollo", "Resuelto", "BL", "despriorizado", "Pruebas"]
# hex sin '#', usados tanto para el fill de la celda Estado en el Excel
# como (con #) para el badge de color en el frontend.
INCIDENCIA_ESTADO_COLORS = {
    "En revisión": "BBDEFB",
    "En desarrollo": "FFF59D",
    "Resuelto": "C8E6C9",
    "BL": "FFCDD2",
    "despriorizado": "E0E0E0",
    "Pruebas": "673AB7",
}

LINKS_SHEET = "Links"
LINKS_COLUMNS = ["Fecha", "URL", "Comentario", "Autor"]

DOCUMENTOS_SHEET = "Documentos"
DOCUMENTOS_COLUMNS = [
    "Fecha", "Nombre", "Comentario", "Proyecto vinculado",
    "Tipo de Documento", "Autor", "Tamaño", "Archivo",
]

DIAGRAMAS_SHEET = "Diagramas"
DIAGRAMAS_COLUMNS = ["Fecha", "Nombre", "Comentario", "Autor", "Tamaño", "Archivo"]

# ---------------------------------------------------------------------------
# Auto-migración de esquema
#
# Problema que resuelve: cada vez que agregamos una columna nueva en el
# código (ej. "Prioridad" en Incidencias), el Excel de trabajo de Hector
# —que ya tiene datos reales cargados— se queda con el esquema viejo, y sin
# esto habría que migrarlo a mano cada vez.
#
# Solución: al arrancar la app, comparamos los headers reales de cada hoja
# contra la lista de columnas que el código espera (las *_COLUMNS de arriba),
# posición por posición. Cualquier columna que falte se INSERTA exactamente
# donde el código la espera (desplazando el resto hacia la derecha con todo
# su contenido) — así ninguna columna existente cambia de posición ni pierde
# su relación con los datos que ya tiene.
#
# Esto cubre el caso más común (agregar una columna nueva, en cualquier
# posición). Lo que NO cubre automáticamente es renombrar el SIGNIFICADO de
# una columna existente (ej. reemplazar Sala/Ubicación por Título) — eso
# sigue necesitando una migración puntual, porque cambiar el significado de
# una columna que ya tiene datos reales requiere criterio, no se puede
# adivinar.
# ---------------------------------------------------------------------------

SCHEMA_BY_SHEET = [
    (PROYECTOS_SHEET, PROYECTOS_COLUMNS),
    (TAREAS_SHEET, COLUMNS),
    (INCIDENCIAS_SHEET, INCIDENCIAS_COLUMNS),
    (PASOS_PROD_SHEET, PASOS_PROD_COLUMNS),
    (LINKS_SHEET, LINKS_COLUMNS),
    (DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS),
    (DIAGRAMAS_SHEET, DIAGRAMAS_COLUMNS),
]


def _ensure_sheet_columns(wb, sheet_name, expected_columns):
    """Compara los encabezados reales de la hoja contra expected_columns, EN ORDEN.
    Si una columna esperada no está donde debería, y tampoco existe en otra
    posición de la hoja, se INSERTA ahí mismo (desplazando las columnas
    siguientes, con todo su contenido, una posición a la derecha) — nunca se
    agrega ciegamente al final, porque el resto del código lee cada hoja por
    posición (columna 1 = primer elemento de la lista, columna 2 = el
    segundo, etc.), así que una columna nueva tiene que insertarse exactamente
    donde el código la espera para no desalinear todo lo que viene después.

    Si una columna esperada YA existe en la hoja (en cualquier posición), no
    se toca — evita duplicados y evita mover columnas que ya tienen datos.

    Devuelve la lista de columnas que tuvo que insertar."""
    if sheet_name not in wb.sheetnames:
        ws = wb.create_sheet(sheet_name)
    else:
        ws = wb[sheet_name]

    added = []
    for target_idx, col_name in enumerate(expected_columns):  # 0-based
        current = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)] if ws.max_row >= 1 else []
        if target_idx < len(current) and current[target_idx] == col_name:
            continue  # ya está exactamente donde corresponde
        if col_name in current:
            continue  # ya existe en otra posición; no la muevo, no toco datos
        insert_at = target_idx + 1  # 1-based
        ws.insert_cols(insert_at)
        cell = ws.cell(row=1, column=insert_at, value=col_name)
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.fill = PatternFill("solid", fgColor="FF2F5496")
        ws.column_dimensions[get_column_letter(insert_at)].width = 18
        added.append(col_name)
    return added


def ensure_schema():
    """Se llama una vez al arrancar la app. Si el Excel de trabajo está en
    un esquema más viejo que el código, lo actualiza en el momento."""
    if not os.path.exists(EXCEL_PATH):
        return
    try:
        wb = load_workbook(EXCEL_PATH)
    except Exception as e:
        print(f"[auto-migración] no se pudo abrir el Excel para revisar el esquema: {e}")
        return

    resumen = {}
    for sheet_name, expected_columns in SCHEMA_BY_SHEET:
        added = _ensure_sheet_columns(wb, sheet_name, expected_columns)
        if added:
            resumen[sheet_name] = added

    if resumen:
        try:
            shutil.copy(EXCEL_PATH, BACKUP_PATH)
        except Exception:
            pass
        wb.save(EXCEL_PATH)
        print("[auto-migración] columnas nuevas agregadas al Excel:")
        for sheet_name, cols in resumen.items():
            print(f"  {sheet_name}: {', '.join(cols)}")
    wb.close()


app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_strict_date(key, value):
    """Convierte el valor de un campo de fecha a un date/datetime real. Si el
    valor no está vacío pero no es una fecha válida (formato AAAA-MM-DD, el que
    entrega <input type="date">), lanza ValueError en vez de guardarlo como
    texto suelto — así ninguna celda de fecha termina con algo que no sea
    una fecha."""
    if value in (None, ""):
        return None
    if isinstance(value, (datetime, date)):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f'"{key}" debe ser una fecha válida (AAAA-MM-DD). Se recibió: "{value}"')


def _to_json_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return value


def _from_json_value(key, value):
    if value in (None, ""):
        return None
    if key in ("Fecha Inicio", "Fecha Fin"):
        return _parse_strict_date(key, value)
    if key == "% Avance":
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    return value


def read_tareas():
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[TAREAS_SHEET]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(COLUMNS))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(COLUMNS, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


def read_proyectos():
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[PROYECTOS_SHEET]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(PROYECTOS_COLUMNS))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(PROYECTOS_COLUMNS, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


def _next_proyecto_color(ws):
    used = {ws.cell(row=r, column=4).value for r in range(2, ws.max_row + 1)}
    for hexcolor in PROYECTOS_PALETTE:
        if f"#{hexcolor}" not in used:
            return f"#{hexcolor}"
    return f"#{PROYECTOS_PALETTE[ws.max_row % len(PROYECTOS_PALETTE)]}"


def create_proyecto(data):
    nombre = (data.get("Nombre") or "").strip()
    if not nombre:
        raise ValueError("El nombre del proyecto es obligatorio")
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PROYECTOS_SHEET]
    existentes = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    if nombre in existentes:
        wb.close()
        raise ValueError(f'Ya existe un proyecto llamado "{nombre}"')
    row_idx = next_row_index(ws)
    ws.cell(row=row_idx, column=1).value = nombre
    ws.cell(row=row_idx, column=2).value = _parse_strict_date("Fecha Inicio", data.get("Fecha Inicio"))
    ws.cell(row=row_idx, column=3).value = _parse_strict_date("Fecha Fin", data.get("Fecha Fin"))
    color = (data.get("Color") or "").strip() or _next_proyecto_color(ws)
    ws.cell(row=row_idx, column=4).value = color
    mostrar = data.get("Mostrar en Roadmap")
    ws.cell(row=row_idx, column=5).value = "Sí" if mostrar in (True, "Sí", "true", "on") else "No"
    wb.save(EXCEL_PATH)
    wb.close()
    return row_idx


def update_proyecto(row_id, data):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PROYECTOS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")

    old_nombre = ws.cell(row=row_id, column=1).value
    updated_tasks = 0

    if "Nombre" in data:
        nuevo_nombre = (data.get("Nombre") or "").strip()
        if not nuevo_nombre:
            wb.close()
            raise ValueError("El nombre del proyecto no puede quedar vacío")
        if nuevo_nombre != old_nombre:
            for r in range(2, ws.max_row + 1):
                if r != row_id and ws.cell(row=r, column=1).value == nuevo_nombre:
                    wb.close()
                    raise ValueError(f'Ya existe un proyecto llamado "{nuevo_nombre}"')
            tareas_ws = wb[TAREAS_SHEET]
            proyecto_col = COLUMNS.index("Proyecto") + 1
            for r in range(2, tareas_ws.max_row + 1):
                if tareas_ws.cell(row=r, column=proyecto_col).value == old_nombre:
                    tareas_ws.cell(row=r, column=proyecto_col).value = nuevo_nombre
                    updated_tasks += 1
            ws.cell(row=row_id, column=1).value = nuevo_nombre

    if "Fecha Inicio" in data:
        ws.cell(row=row_id, column=2).value = _parse_strict_date("Fecha Inicio", data.get("Fecha Inicio"))
    if "Fecha Fin" in data:
        ws.cell(row=row_id, column=3).value = _parse_strict_date("Fecha Fin", data.get("Fecha Fin"))
    if "Color" in data and (data.get("Color") or "").strip():
        ws.cell(row=row_id, column=4).value = data.get("Color").strip()
    if "Mostrar en Roadmap" in data:
        mostrar = data.get("Mostrar en Roadmap")
        ws.cell(row=row_id, column=5).value = "Sí" if mostrar in (True, "Sí", "true", "on") else "No"

    wb.save(EXCEL_PATH)
    wb.close()
    return {"updated_tasks": updated_tasks}


def delete_proyecto(row_id):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PROYECTOS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    ws.delete_rows(row_id, 1)
    wb.save(EXCEL_PATH)
    wb.close()


def _roadmap_sort_key(t):
    """Orden de las tareas clave dentro de un proyecto en el Roadmap: las que
    tienen un 'Orden Roadmap' manual (asignado al usar las flechas ▲▼) van
    primero, en ese orden; el resto se ordena por Fecha Inicio (más antigua
    primero) — así el Roadmap se ve en cascada por defecto, sin que el usuario
    tenga que ordenar nada a mano, pero permitiendo ajustar casos puntuales."""
    orden = t.get("Orden Roadmap")
    if orden not in (None, ""):
        try:
            return (0, float(orden))
        except (TypeError, ValueError):
            pass
    return (1, t.get("Fecha Inicio") or "")


def read_roadmap():
    """Vista derivada para el Roadmap: cada proyecto con su rango estimado, y
    como hijas solo las tareas marcadas 'Clave' que apuntan a ese proyecto —
    usando la fecha real de cada tarea, no una copia manual."""
    proyectos = [p for p in read_proyectos() if p.get("Mostrar en Roadmap") != "No"]
    tareas = read_tareas()
    sin_fecha = []
    for p in proyectos:
        hijas = []
        for t in tareas:
            if t.get("Proyecto") != p["Nombre"] or t.get("Clave") != "Sí":
                continue
            label = t["Tarea"] + (f" · {t['Subtarea']}" if t.get("Subtarea") else "")
            item = {
                "row_id": t["row_id"],
                "label": label,
                "Fecha Inicio": t.get("Fecha Inicio"),
                "Fecha Fin": t.get("Fecha Fin"),
                "Estado": t.get("Estado"),
                "Notas": t.get("Notas"),
                "Orden Roadmap": t.get("Orden Roadmap"),
            }
            if not t.get("Fecha Inicio") or not t.get("Fecha Fin"):
                sin_fecha.append({"row_id": t["row_id"], "label": label, "proyecto": p["Nombre"]})
            else:
                hijas.append(item)
        hijas.sort(key=_roadmap_sort_key)
        p["tareas"] = hijas
    return {"proyectos": proyectos, "sin_fecha": sin_fecha}


def read_listas():
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[LISTAS_SHEET]
    headers = [c.value for c in ws[1]]
    result = {h: [] for h in headers if h}
    for row_idx in range(2, ws.max_row + 1):
        for col_idx, h in enumerate(headers, start=1):
            if not h:
                continue
            v = ws.cell(row=row_idx, column=col_idx).value
            if v not in (None, "") and v not in result[h]:
                result[h].append(v)
    wb.close()
    return result


# Which Listas columns are editable via the "Equipo y Proyectos" module, and
# which sheet+column each one feeds into (for cascade rename / usage counts).
# A list column can feed more than one sheet (e.g. Responsable is shared by
# Tareas and Incidencias).
LISTAS_EDITABLE_COLUMNS = {
    "Responsable": [
        (TAREAS_SHEET, COLUMNS, "Responsable"),
        (INCIDENCIAS_SHEET, INCIDENCIAS_COLUMNS, "Responsable (seguimiento)"),
        (INCIDENCIAS_SHEET, INCIDENCIAS_COLUMNS, "Responsable (desarrollo)"),
    ],
    "Producto": [(INCIDENCIAS_SHEET, INCIDENCIAS_COLUMNS, "Producto")],
    "Tipo de incidencia": [(INCIDENCIAS_SHEET, INCIDENCIAS_COLUMNS, "Tipo de incidencia")],
    "Tipo de Documento": [(DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS, "Tipo de Documento")],
}


def _listas_column_index(ws, column_name):
    headers = [c.value for c in ws[1]]
    if column_name not in headers:
        raise ValueError(f"La lista '{column_name}' no existe")
    return headers.index(column_name) + 1


def add_lista_item(column_name, value):
    if column_name not in LISTAS_EDITABLE_COLUMNS:
        raise ValueError("Esa lista no es editable desde aquí")
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LISTAS_SHEET]
    col_idx = _listas_column_index(ws, column_name)

    target_row = ws.max_row + 1
    for r in range(2, ws.max_row + 2):
        v = ws.cell(row=r, column=col_idx).value
        if v is None:
            target_row = r
            break
        if v == value:
            wb.close()
            raise ValueError("Ese valor ya existe en la lista")

    ws.cell(row=target_row, column=col_idx).value = value
    wb.save(EXCEL_PATH)
    wb.close()


def rename_lista_item(column_name, old_value, new_value, cascade=True):
    if column_name not in LISTAS_EDITABLE_COLUMNS:
        raise ValueError("Esa lista no es editable desde aquí")
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LISTAS_SHEET]
    col_idx = _listas_column_index(ws, column_name)

    found = False
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=col_idx).value == old_value:
            ws.cell(row=r, column=col_idx).value = new_value
            found = True
            break
    if not found:
        wb.close()
        raise ValueError("No se encontró ese valor en la lista")

    counts_by_sheet = {}
    if cascade:
        for sheet_name, columns_list, field in LISTAS_EDITABLE_COLUMNS[column_name]:
            target_ws = wb[sheet_name]
            field_col = columns_list.index(field) + 1
            for r in range(2, target_ws.max_row + 1):
                if target_ws.cell(row=r, column=field_col).value == old_value:
                    target_ws.cell(row=r, column=field_col).value = new_value
                    counts_by_sheet[sheet_name] = counts_by_sheet.get(sheet_name, 0) + 1

    wb.save(EXCEL_PATH)
    wb.close()
    return {
        "updated_tasks": counts_by_sheet.get(TAREAS_SHEET, 0),
        "updated_incidencias": counts_by_sheet.get(INCIDENCIAS_SHEET, 0),
        "updated_documentos": counts_by_sheet.get(DOCUMENTOS_SHEET, 0),
    }


def delete_lista_item(column_name, value):
    if column_name not in LISTAS_EDITABLE_COLUMNS:
        raise ValueError("Esa lista no es editable desde aquí")
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LISTAS_SHEET]
    col_idx = _listas_column_index(ws, column_name)

    remaining = []
    found = False
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=col_idx).value
        if v is None:
            continue
        if v == value and not found:
            found = True
            continue
        remaining.append(v)

    if not found:
        wb.close()
        raise ValueError("No se encontró ese valor en la lista")

    for i, r in enumerate(range(2, ws.max_row + 1)):
        ws.cell(row=r, column=col_idx).value = remaining[i] if i < len(remaining) else None

    wb.save(EXCEL_PATH)
    wb.close()


def backup_file():
    if os.path.exists(EXCEL_PATH):
        shutil.copy2(EXCEL_PATH, BACKUP_PATH)


def next_row_index(ws):
    """First fully-empty row after the header, appending at the end."""
    row_idx = ws.max_row + 1
    return row_idx


def read_pasos_prod():
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PASOS_PROD_SHEET]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(PASOS_PROD_COLUMNS))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(PASOS_PROD_COLUMNS, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


def create_paso_prod(data):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PASOS_PROD_SHEET]
    row_idx = next_row_index(ws)
    for col_idx, key in enumerate(PASOS_PROD_COLUMNS, start=1):
        value = data.get(key)
        value = _parse_strict_date(key, value) if key == "Fecha" else (value or None)
        ws.cell(row=row_idx, column=col_idx).value = value
    wb.save(EXCEL_PATH)
    wb.close()
    return row_idx


def update_paso_prod(row_id, data):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PASOS_PROD_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    for col_idx, key in enumerate(PASOS_PROD_COLUMNS, start=1):
        if key in data:
            value = data.get(key)
            value = _parse_strict_date(key, value) if key == "Fecha" else (value or None)
            ws.cell(row=row_id, column=col_idx).value = value
    wb.save(EXCEL_PATH)
    wb.close()


def delete_paso_prod(row_id):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PASOS_PROD_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    ws.delete_rows(row_id, 1)
    wb.save(EXCEL_PATH)
    wb.close()


def _incidencia_from_json(key, value):
    if value in (None, ""):
        return None
    if key in INCIDENCIAS_DATE_FIELDS:
        return _parse_strict_date(key, value)
    if key in ("Cantidad", "Prioridad"):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    return value


def _apply_incidencia_estado_fill(ws, row_idx, estado):
    col_idx = INCIDENCIAS_COLUMNS.index("Estado") + 1
    cell = ws.cell(row=row_idx, column=col_idx)
    hex_color = INCIDENCIA_ESTADO_COLORS.get(estado)
    if hex_color:
        cell.fill = PatternFill("solid", fgColor=hex_color)
    else:
        cell.fill = PatternFill(fill_type=None)


def read_incidencias():
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[INCIDENCIAS_SHEET]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(INCIDENCIAS_COLUMNS))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(INCIDENCIAS_COLUMNS, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


INCIDENCIAS_STRICT_LIST_FIELDS = {
    "Responsable (seguimiento)": "Responsable",
    "Responsable (desarrollo)": "Responsable",
}


def _validate_incidencia_strict_fields(data):
    """Los campos en INCIDENCIAS_STRICT_LIST_FIELDS solo aceptan valores que ya
    existan en la lista editable correspondiente (Equipo y Proyectos) — nunca
    texto libre, para no ensuciar los datos con nombres escritos a mano."""
    listas = None
    for field, lista_col in INCIDENCIAS_STRICT_LIST_FIELDS.items():
        if field not in data:
            continue
        value = (data.get(field) or "").strip() if isinstance(data.get(field), str) else data.get(field)
        if not value:
            continue
        if listas is None:
            listas = read_listas()
        permitidos = listas.get(lista_col, [])
        if value not in permitidos:
            raise ValueError(f'"{value}" no está en la lista de {lista_col}. Agrégalo primero en Equipo y Proyectos.')


def create_incidencia(data):
    _validate_incidencia_strict_fields(data)
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[INCIDENCIAS_SHEET]
    row_idx = next_row_index(ws)
    for col_idx, key in enumerate(INCIDENCIAS_COLUMNS, start=1):
        ws.cell(row=row_idx, column=col_idx).value = _incidencia_from_json(key, data.get(key))
    _apply_incidencia_estado_fill(ws, row_idx, data.get("Estado"))
    wb.save(EXCEL_PATH)
    wb.close()
    return row_idx


def update_incidencia(row_id, data):
    _validate_incidencia_strict_fields(data)
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[INCIDENCIAS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    for col_idx, key in enumerate(INCIDENCIAS_COLUMNS, start=1):
        if key in data:
            ws.cell(row=row_id, column=col_idx).value = _incidencia_from_json(key, data.get(key))
    if "Estado" in data:
        _apply_incidencia_estado_fill(ws, row_id, data.get("Estado"))
    wb.save(EXCEL_PATH)
    wb.close()


def delete_incidencia(row_id):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[INCIDENCIAS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    ws.delete_rows(row_id, 1)
    wb.save(EXCEL_PATH)
    wb.close()


def import_incidencias_from_csv(file_bytes):
    try:
        raw = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = file_bytes.decode("latin-1")

    # Try to sniff the delimiter (Excel-exported CSVs from Chile often use ';').
    sample = raw[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("El archivo CSV está vacío o no tiene encabezados")

    fieldnames = [f.strip() for f in reader.fieldnames]
    missing = [c for c in INCIDENCIAS_COLUMNS if c not in fieldnames]

    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[INCIDENCIAS_SHEET]

    imported = 0
    errors = []
    listas_cache = read_listas()
    for i, raw_row in enumerate(reader, start=2):
        row = {(k.strip() if k else k): v for k, v in raw_row.items()}
        try:
            for field, lista_col in INCIDENCIAS_STRICT_LIST_FIELDS.items():
                val = (row.get(field) or "").strip() if isinstance(row.get(field), str) else row.get(field)
                if val and val not in listas_cache.get(lista_col, []):
                    raise ValueError(f'"{val}" no está en la lista de {lista_col}. Agrégalo primero en Equipo y Proyectos.')
            row_idx = next_row_index(ws)
            for col_idx, key in enumerate(INCIDENCIAS_COLUMNS, start=1):
                value = row.get(key)
                value = value.strip() if isinstance(value, str) else value
                ws.cell(row=row_idx, column=col_idx).value = _incidencia_from_json(key, value)
            _apply_incidencia_estado_fill(ws, row_idx, row.get("Estado"))
            imported += 1
        except Exception as e:
            errors.append(f"Fila {i} del CSV: {e}")

    wb.save(EXCEL_PATH)
    wb.close()
    return {"imported": imported, "errors": errors, "missing_columns": missing}


# ---------------------------------------------------------------------------
# Links (hoja simple, mismo patrón que Pasos a Prod)
# ---------------------------------------------------------------------------

def read_links():
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[LINKS_SHEET]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(LINKS_COLUMNS))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(LINKS_COLUMNS, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


def create_link(data):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LINKS_SHEET]
    row_idx = next_row_index(ws)
    values = {
        "Fecha": datetime.now(),
        "URL": (data.get("URL") or "").strip(),
        "Comentario": (data.get("Comentario") or "").strip(),
        "Autor": (data.get("Autor") or "").strip(),
    }
    for col_idx, key in enumerate(LINKS_COLUMNS, start=1):
        ws.cell(row=row_idx, column=col_idx).value = values.get(key) or None
    wb.save(EXCEL_PATH)
    wb.close()
    return row_idx


def update_link(row_id, data):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LINKS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    for col_idx, key in enumerate(LINKS_COLUMNS, start=1):
        if key in data:
            val = (data.get(key) or "").strip()
            ws.cell(row=row_id, column=col_idx).value = val or None
    wb.save(EXCEL_PATH)
    wb.close()


def delete_link(row_id):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[LINKS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    ws.delete_rows(row_id, 1)
    wb.save(EXCEL_PATH)
    wb.close()


# ---------------------------------------------------------------------------
# Documentos y Diagramas: metadata en Excel, bytes en disco (data/documentos,
# data/diagramas). Genérico porque ambos módulos comparten exactamente el
# mismo patrón de alta/baja/descarga.
# ---------------------------------------------------------------------------

def _safe_filename(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "archivo")
    return name[:120] or "archivo"


def read_file_records(sheet_name, columns):
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[sheet_name]
    rows = []
    for row_idx in range(2, ws.max_row + 1):
        values = [ws.cell(row=row_idx, column=c + 1).value for c in range(len(columns))]
        if all(v is None for v in values):
            continue
        row_dict = {"row_id": row_idx}
        for key, val in zip(columns, values):
            row_dict[key] = _to_json_value(val)
        rows.append(row_dict)
    wb.close()
    return rows


def create_file_record(sheet_name, columns, folder, file_storage, extra_fields):
    original_name = (file_storage.filename or "archivo").strip()
    if not original_name:
        raise ValueError("El archivo no tiene nombre")
    file_bytes = file_storage.read()
    if not file_bytes:
        raise ValueError("El archivo está vacío")

    os.makedirs(folder, exist_ok=True)
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[sheet_name]
    row_idx = next_row_index(ws)

    stored_name = f"{row_idx}-{_safe_filename(original_name)}"
    with open(os.path.join(folder, stored_name), "wb") as f:
        f.write(file_bytes)

    values = {
        "Fecha": datetime.now(),
        "Nombre": original_name,
        "Tamaño": len(file_bytes),
        "Archivo": stored_name,
    }
    values.update({k: (v or None) for k, v in extra_fields.items()})

    for col_idx, key in enumerate(columns, start=1):
        ws.cell(row=row_idx, column=col_idx).value = values.get(key)
    wb.save(EXCEL_PATH)
    wb.close()
    return row_idx


def get_file_record(sheet_name, columns, row_id):
    wb = load_workbook(EXCEL_PATH, data_only=False)
    ws = wb[sheet_name]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        return None
    values = {key: ws.cell(row=row_id, column=idx).value for idx, key in enumerate(columns, start=1)}
    wb.close()
    return values


def delete_file_record(sheet_name, columns, folder, row_id):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[sheet_name]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")
    archivo_col = columns.index("Archivo") + 1
    stored_name = ws.cell(row=row_id, column=archivo_col).value
    ws.delete_rows(row_id, 1)
    wb.save(EXCEL_PATH)
    wb.close()
    if stored_name:
        stored_path = os.path.join(folder, stored_name)
        if os.path.exists(stored_path):
            os.remove(stored_path)


def _unmerge_all(ws):
    """Merged cells (inherited from the original spreadsheet's month/week headers)
    block direct writes to non-anchor cells. Flatten them once so every cell is
    independently editable — our forward-fill read logic already handles the
    resulting empty cells correctly."""
    for merged_range in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(merged_range))


# ---------------------------------------------------------------------------
# Vínculo Tareas -> Planificación ("desarrollo clave" ligado a un proyecto)
#
# Deliberadamente NO guardamos el número de fila de Planificación en la hoja
# Tareas: cualquier alta/baja/reordenamiento posterior en Planificación
# desplaza filas, y un número guardado se volvería obsoleto silenciosamente
# (apuntando a la fila equivocada). En cambio, cada sincronización vuelve a
# ubicar la fila espejo buscando por (proyecto, nombre de tarea) en el
# momento, así siempre opera sobre datos frescos.
# ---------------------------------------------------------------------------

def _roadmap_task_label(tarea, subtarea):
    tarea = (tarea or "").strip()
    subtarea = (subtarea or "").strip()
    if not tarea:
        return None
    return f"{tarea} · {subtarea}" if subtarea else tarea


def _find_planificacion_section_row_in_wb(ws, name):
    if not name:
        return None
    name = name.strip()
    for row in range(3, ws.max_row + 1):
        cell_a = ws.cell(row=row, column=1)
        if _is_section_header(cell_a) and cell_a.value and cell_a.value.strip() == name:
            return row
    return None


def _find_planificacion_task_row_in_wb(ws, section_name, task_name):
    if not section_name or not task_name:
        return None
    section_name = section_name.strip()
    task_name = task_name.strip()
    in_section = False
    for row in range(3, ws.max_row + 1):
        cell_a = ws.cell(row=row, column=1)
        if _is_section_header(cell_a):
            in_section = bool(cell_a.value and cell_a.value.strip() == section_name)
            continue
        if in_section and cell_a.value and cell_a.value.strip() == task_name:
            return row
    return None


def _add_planificacion_section_in_wb(ws, name):
    row = ws.max_row + 1
    cell = ws.cell(row=row, column=1)
    cell.value = name
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="FFFF00")
    return row


def _add_planificacion_task_in_wb(ws, section_row, name, notas):
    insert_at = ws.max_row + 1
    found_section = False
    for row in range(3, ws.max_row + 1):
        cell_a = ws.cell(row=row, column=1)
        if _is_section_header(cell_a):
            if row == section_row:
                found_section = True
                continue
            if found_section:
                insert_at = row
                break
    ws.insert_rows(insert_at)
    ws.cell(row=insert_at, column=1).value = name
    ws.cell(row=insert_at, column=2).value = notas or None
    return insert_at


def sync_tarea_roadmap(wb, old_clave, old_proyecto, old_name, new_clave, new_proyecto, new_name, notas):
    """Mantiene sincronizada, dentro del mismo workbook ya abierto (sin guardar
    ni cerrar), la fila espejo en Planificación de una tarea marcada 'Clave'."""
    plan_ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(plan_ws)

    existing_row = None
    if old_clave:
        existing_row = _find_planificacion_task_row_in_wb(plan_ws, old_proyecto, old_name)

    if not new_clave:
        if existing_row:
            plan_ws.delete_rows(existing_row, 1)
        return

    if not new_name:
        return  # sin nombre de tarea no hay nada que reflejar en el Roadmap

    if existing_row and (old_proyecto or "").strip() == (new_proyecto or "").strip():
        plan_ws.cell(row=existing_row, column=1).value = new_name
        plan_ws.cell(row=existing_row, column=2).value = notas or None
        return

    if existing_row:
        plan_ws.delete_rows(existing_row, 1)

    section_row = _find_planificacion_section_row_in_wb(plan_ws, new_proyecto)
    if section_row is None:
        section_row = _add_planificacion_section_in_wb(plan_ws, new_proyecto)
    _add_planificacion_task_in_wb(plan_ws, section_row, new_name, notas)


def _get_fill_color(cell):
    fill = cell.fill
    if not fill or fill.patternType is None:
        return None
    fg = fill.fgColor
    if fg.type == "rgb" and fg.rgb and fg.rgb not in ("00000000", None):
        rgb = fg.rgb
        if len(rgb) == 8:
            rgb = rgb[2:]
        return f"#{rgb}"
    if fg.type == "theme":
        return PLANIFICACION_THEME_COLORS.get(fg.theme, "#D8DCE3")
    return "#D8DCE3"


def _is_section_header(cell):
    name = cell.value
    if not name:
        return False
    if name.strip() in PLANIFICACION_SECTION_NAMES:
        return True
    return bool(cell.font and cell.font.bold)


def read_planificacion():
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]

    weeks = []
    last_month, last_week = None, None
    last_real_col = PLANIFICACION_FIRST_WEEK_COL - 1
    for col in range(PLANIFICACION_FIRST_WEEK_COL, ws.max_column + 1):
        v1 = ws.cell(row=1, column=col).value
        v2 = ws.cell(row=2, column=col).value
        if v1:
            last_month = v1
        if v2:
            last_week = v2
        if v1 or v2:
            last_real_col = col
        weeks.append({"col": col, "month": last_month, "week": last_week})

    # drop trailing "ghost" columns left over after a column delete (openpyxl
    # doesn't always shrink max_column immediately)
    weeks = [w for w in weeks if w["col"] <= last_real_col]

    sections = []
    current = None
    for row in range(3, ws.max_row + 1):
        cell_a = ws.cell(row=row, column=1)
        name = cell_a.value
        if _is_section_header(cell_a):
            header_cells = {}
            for col in range(PLANIFICACION_FIRST_WEEK_COL, ws.max_column + 1):
                c = ws.cell(row=row, column=col)
                color = _get_fill_color(c)
                label = c.value
                if color or label:
                    header_cells[str(col)] = {"active": True, "label": label, "color": color or PLANIFICACION_DEFAULT_COLOR}
            current = {"row": row, "name": name.strip(), "cells": header_cells, "tasks": []}
            sections.append(current)
            continue
        if not name:
            continue
        if current is None:
            current = {"row": None, "name": "General", "cells": {}, "tasks": []}
            sections.append(current)
        notas = ws.cell(row=row, column=2).value
        cells = {}
        for col in range(PLANIFICACION_FIRST_WEEK_COL, ws.max_column + 1):
            c = ws.cell(row=row, column=col)
            color = _get_fill_color(c)
            label = c.value
            if color or label:
                cells[str(col)] = {"active": True, "label": label, "color": color or PLANIFICACION_DEFAULT_COLOR}
        current["tasks"].append({"row": row, "name": name, "notas": notas, "cells": cells})

    wb.close()
    return {"weeks": weeks, "sections": sections}


def write_planificacion_cell(row, col, active, label, color):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    cell = ws.cell(row=row, column=col)
    if active:
        cell.value = label or None
        cell.fill = PatternFill("solid", fgColor=(color or PLANIFICACION_DEFAULT_COLOR).lstrip("#"))
    else:
        cell.value = None
        cell.fill = PatternFill(fill_type=None)
    wb.save(EXCEL_PATH)
    wb.close()


def write_planificacion_cells_batch(cells, active, label, color):
    """Apply the same active/label/color to a list of (row, col) cells in one save —
    used for range selections (drag across several weeks at once)."""
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    for row, col in cells:
        cell = ws.cell(row=row, column=col)
        if active:
            cell.value = label or None
            cell.fill = PatternFill("solid", fgColor=(color or PLANIFICACION_DEFAULT_COLOR).lstrip("#"))
        else:
            cell.value = None
            cell.fill = PatternFill(fill_type=None)
    wb.save(EXCEL_PATH)
    wb.close()


def add_planificacion_section(name):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    row = ws.max_row + 1
    cell = ws.cell(row=row, column=1)
    cell.value = name
    cell.font = Font(bold=True)
    cell.fill = PatternFill("solid", fgColor="FFFF00")
    wb.save(EXCEL_PATH)
    wb.close()
    return row


def add_planificacion_task(section_row, name, notas):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)

    # find the row right before the next section header (or end of sheet)
    insert_at = ws.max_row + 1
    found_section = False
    for row in range(3, ws.max_row + 1):
        cell_a = ws.cell(row=row, column=1)
        if _is_section_header(cell_a):
            if row == section_row:
                found_section = True
                continue
            if found_section:
                insert_at = row
                break

    ws.insert_rows(insert_at)
    ws.cell(row=insert_at, column=1).value = name
    ws.cell(row=insert_at, column=2).value = notas or None
    wb.save(EXCEL_PATH)
    wb.close()
    return insert_at


def delete_planificacion_week(col):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    if col < PLANIFICACION_FIRST_WEEK_COL or col > ws.max_column:
        wb.close()
        raise ValueError("Semana inválida")
    ws.delete_cols(col, 1)
    wb.save(EXCEL_PATH)
    wb.close()


def update_planificacion_week(col, month, week):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    if col < PLANIFICACION_FIRST_WEEK_COL or col > ws.max_column:
        wb.close()
        raise ValueError("Semana inválida")
    if month is not None:
        ws.cell(row=1, column=col).value = month or None
    if week is not None:
        ws.cell(row=2, column=col).value = week or None
    wb.save(EXCEL_PATH)
    wb.close()


def add_planificacion_month(month_name, num_weeks):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    start_col = ws.max_column + 1
    for i in range(num_weeks):
        col = start_col + i
        ws.cell(row=1, column=col).value = month_name if i == 0 else None
        ws.cell(row=2, column=col).value = f"sem {i + 1}"
    wb.save(EXCEL_PATH)
    wb.close()
    return start_col


def update_planificacion_task(row, name, notas):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    cell_a = ws.cell(row=row, column=1)
    if _is_section_header(cell_a):
        wb.close()
        raise ValueError("Esa fila es un proyecto, no una tarea.")
    cell_a.value = name
    ws.cell(row=row, column=2).value = notas or None
    wb.save(EXCEL_PATH)
    wb.close()


def update_planificacion_section(row, name):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    cell_a = ws.cell(row=row, column=1)
    if not _is_section_header(cell_a):
        wb.close()
        raise ValueError("Esa fila no corresponde a un proyecto")
    cell_a.value = name
    cell_a.font = Font(bold=True)  # keep it detectable as a header even if the name changes
    wb.save(EXCEL_PATH)
    wb.close()


def move_planificacion_task(row, direction):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)

    cell_a = ws.cell(row=row, column=1)
    if _is_section_header(cell_a):
        wb.close()
        raise ValueError("No se puede reordenar un proyecto con esta acción")

    target_row = row - 1 if direction == "up" else row + 1
    if target_row < 3 or target_row > ws.max_row:
        wb.close()
        raise ValueError("Ya está en el límite del proyecto")

    target_a = ws.cell(row=target_row, column=1)
    if target_a.value is None or _is_section_header(target_a):
        wb.close()
        raise ValueError("Ya está en el límite del proyecto")

    for col in range(1, ws.max_column + 1):
        c1 = ws.cell(row=row, column=col)
        c2 = ws.cell(row=target_row, column=col)
        v1, v2 = c1.value, c2.value
        f1, f2 = copy(c1.fill), copy(c2.fill)
        c1.value, c2.value = v2, v1
        c1.fill, c2.fill = f2, f1

    wb.save(EXCEL_PATH)
    wb.close()
    return target_row


def delete_planificacion_task(row):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    cell_a = ws.cell(row=row, column=1)
    if _is_section_header(cell_a):
        wb.close()
        raise ValueError("Esa fila es un proyecto, no una tarea. Usa el borrado de proyecto en su lugar.")
    ws.delete_rows(row, 1)
    wb.save(EXCEL_PATH)
    wb.close()


def delete_planificacion_section(row):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)
    cell_a = ws.cell(row=row, column=1)
    if not _is_section_header(cell_a):
        wb.close()
        raise ValueError("Esa fila no corresponde a un proyecto")

    end_row = ws.max_row
    for r in range(row + 1, ws.max_row + 1):
        if _is_section_header(ws.cell(row=r, column=1)):
            end_row = r - 1
            break
    ws.delete_rows(row, end_row - row + 1)
    wb.save(EXCEL_PATH)
    wb.close()


def delete_planificacion_month(month_name):
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[PLANIFICACION_SHEET]
    _unmerge_all(ws)

    cols_to_delete = []
    last_month = None
    for col in range(PLANIFICACION_FIRST_WEEK_COL, ws.max_column + 1):
        v1 = ws.cell(row=1, column=col).value
        if v1:
            last_month = v1
        if last_month == month_name:
            cols_to_delete.append(col)

    if not cols_to_delete:
        wb.close()
        raise ValueError(f"No se encontró el mes '{month_name}'")

    for col in sorted(cols_to_delete, reverse=True):
        ws.delete_cols(col, 1)
    wb.save(EXCEL_PATH)
    wb.close()


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/tareas", methods=["GET"])
def get_tareas():
    try:
        return jsonify({"ok": True, "data": read_tareas()})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tareas", methods=["POST"])
def create_tarea():
    payload = request.get_json(force=True)
    try:
        backup_file()
        wb = load_workbook(EXCEL_PATH)
        ws = wb[TAREAS_SHEET]
        row_idx = next_row_index(ws)
        for col_idx, key in enumerate(COLUMNS, start=1):
            ws.cell(row=row_idx, column=col_idx).value = _from_json_value(key, payload.get(key))

        new_clave = payload.get("Clave") == "Sí"
        new_proyecto = (payload.get("Proyecto") or "").strip()
        new_name = _roadmap_task_label(payload.get("Tarea"), payload.get("Subtarea"))
        notas = (payload.get("Responsable") or "").strip()
        sync_tarea_roadmap(
            wb, old_clave=False, old_proyecto=None, old_name=None,
            new_clave=new_clave, new_proyecto=new_proyecto, new_name=new_name, notas=notas,
        )

        wb.save(EXCEL_PATH)
        wb.close()
        return jsonify({"ok": True, "row_id": row_idx})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tareas/<int:row_id>", methods=["PUT"])
def update_tarea(row_id):
    payload = request.get_json(force=True)
    try:
        backup_file()
        wb = load_workbook(EXCEL_PATH)
        ws = wb[TAREAS_SHEET]
        if row_id < 2 or row_id > ws.max_row:
            return jsonify({"ok": False, "error": "Fila inválida"}), 400

        old_values = {key: ws.cell(row=row_id, column=idx).value for idx, key in enumerate(COLUMNS, start=1)}

        for col_idx, key in enumerate(COLUMNS, start=1):
            if key in payload:
                ws.cell(row=row_id, column=col_idx).value = _from_json_value(key, payload.get(key))

        old_clave = old_values.get("Clave") == "Sí"
        old_proyecto = (old_values.get("Proyecto") or "").strip()
        old_name = _roadmap_task_label(old_values.get("Tarea"), old_values.get("Subtarea"))

        new_clave = (payload["Clave"] if "Clave" in payload else old_values.get("Clave")) == "Sí"
        new_proyecto = ((payload["Proyecto"] if "Proyecto" in payload else old_values.get("Proyecto")) or "").strip()
        new_tarea = payload["Tarea"] if "Tarea" in payload else old_values.get("Tarea")
        new_subtarea = payload["Subtarea"] if "Subtarea" in payload else old_values.get("Subtarea")
        new_name = _roadmap_task_label(new_tarea, new_subtarea)
        new_responsable = payload["Responsable"] if "Responsable" in payload else old_values.get("Responsable")
        notas = (new_responsable or "").strip()

        sync_tarea_roadmap(
            wb, old_clave=old_clave, old_proyecto=old_proyecto, old_name=old_name,
            new_clave=new_clave, new_proyecto=new_proyecto, new_name=new_name, notas=notas,
        )

        wb.save(EXCEL_PATH)
        wb.close()
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def move_roadmap_task(row_id, direction):
    """Mueve una tarea clave arriba/abajo dentro del orden en cascada de su
    proyecto en el Roadmap. La primera vez que se mueve una tarea de un
    proyecto, se fija un 'Orden Roadmap' explícito para TODAS sus tareas
    clave (según el orden efectivo que tenían en ese momento — manual si ya
    existía, o por fecha si no); de ahí en adelante ese proyecto queda bajo
    control manual. Tareas clave nuevas que se agreguen después, sin orden
    asignado, aparecerán al final hasta que también se reordenen a mano."""
    backup_file()
    wb = load_workbook(EXCEL_PATH)
    ws = wb[TAREAS_SHEET]
    if row_id < 2 or row_id > ws.max_row:
        wb.close()
        raise ValueError("Fila inválida")

    proyecto_col = COLUMNS.index("Proyecto") + 1
    clave_col = COLUMNS.index("Clave") + 1
    orden_col = COLUMNS.index("Orden Roadmap") + 1
    fecha_inicio_col = COLUMNS.index("Fecha Inicio") + 1

    proyecto = ws.cell(row=row_id, column=proyecto_col).value
    if ws.cell(row=row_id, column=clave_col).value != "Sí":
        wb.close()
        raise ValueError("Esta tarea no está marcada como desarrollo clave")

    # Reunir todas las tareas clave del mismo proyecto, con su orden efectivo actual.
    hermanas = []
    for r in range(2, ws.max_row + 1):
        if ws.cell(row=r, column=proyecto_col).value != proyecto:
            continue
        if ws.cell(row=r, column=clave_col).value != "Sí":
            continue
        fi = ws.cell(row=r, column=fecha_inicio_col).value
        hermanas.append({
            "row": r,
            "orden": ws.cell(row=r, column=orden_col).value,
            "fecha_inicio": fi.strftime("%Y-%m-%d") if isinstance(fi, (datetime, date)) else (fi or ""),
        })

    hermanas.sort(key=lambda t: _roadmap_sort_key({"Orden Roadmap": t["orden"], "Fecha Inicio": t["fecha_inicio"]}))

    idx = next((i for i, t in enumerate(hermanas) if t["row"] == row_id), None)
    if idx is None:
        wb.close()
        raise ValueError("No se encontró la tarea entre sus hermanas")

    target_idx = idx - 1 if direction == "up" else idx + 1
    if target_idx < 0 or target_idx >= len(hermanas):
        wb.close()
        raise ValueError("Ya está en el límite del proyecto")

    hermanas[idx], hermanas[target_idx] = hermanas[target_idx], hermanas[idx]

    for i, t in enumerate(hermanas):
        ws.cell(row=t["row"], column=orden_col).value = i

    wb.save(EXCEL_PATH)
    wb.close()


@app.route("/api/tareas/<int:row_id>", methods=["DELETE"])
def delete_tarea(row_id):
    try:
        backup_file()
        wb = load_workbook(EXCEL_PATH)
        ws = wb[TAREAS_SHEET]
        if row_id < 2 or row_id > ws.max_row:
            return jsonify({"ok": False, "error": "Fila inválida"}), 400

        clave = ws.cell(row=row_id, column=COLUMNS.index("Clave") + 1).value == "Sí"
        proyecto = ws.cell(row=row_id, column=COLUMNS.index("Proyecto") + 1).value
        tarea_name = _roadmap_task_label(
            ws.cell(row=row_id, column=COLUMNS.index("Tarea") + 1).value,
            ws.cell(row=row_id, column=COLUMNS.index("Subtarea") + 1).value,
        )

        ws.delete_rows(row_id, 1)

        if clave:
            sync_tarea_roadmap(
                wb, old_clave=True, old_proyecto=proyecto, old_name=tarea_name,
                new_clave=False, new_proyecto=None, new_name=None, notas=None,
            )

        wb.save(EXCEL_PATH)
        wb.close()
        return jsonify({"ok": True})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pasos-prod", methods=["GET"])
def get_pasos_prod():
    try:
        return jsonify({"ok": True, "data": read_pasos_prod()})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pasos-prod", methods=["POST"])
def create_paso_prod_route():
    payload = request.get_json(force=True)
    try:
        row_id = create_paso_prod(payload)
        return jsonify({"ok": True, "row_id": row_id})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pasos-prod/<int:row_id>", methods=["PUT"])
def update_paso_prod_route(row_id):
    payload = request.get_json(force=True)
    try:
        update_paso_prod(row_id, payload)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/pasos-prod/<int:row_id>", methods=["DELETE"])
def delete_paso_prod_route(row_id):
    try:
        delete_paso_prod(row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidencias", methods=["GET"])
def get_incidencias():
    try:
        return jsonify({
            "ok": True,
            "data": read_incidencias(),
            "estados": INCIDENCIA_ESTADOS,
            "estado_colors": {k: f"#{v}" for k, v in INCIDENCIA_ESTADO_COLORS.items()},
        })
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidencias", methods=["POST"])
def create_incidencia_route():
    payload = request.get_json(force=True)
    try:
        row_id = create_incidencia(payload)
        return jsonify({"ok": True, "row_id": row_id})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidencias/<int:row_id>", methods=["PUT"])
def update_incidencia_route(row_id):
    payload = request.get_json(force=True)
    try:
        update_incidencia(row_id, payload)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidencias/<int:row_id>", methods=["DELETE"])
def delete_incidencia_route(row_id):
    try:
        delete_incidencia(row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/incidencias/import-csv", methods=["POST"])
def import_incidencias_csv_route():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No se recibió ningún archivo CSV"}), 400
    try:
        result = import_incidencias_from_csv(file.read())
        return jsonify({"ok": True, **result})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/links", methods=["GET"])
def get_links():
    try:
        return jsonify({"ok": True, "data": read_links()})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/links", methods=["POST"])
def create_link_route():
    payload = request.get_json(force=True)
    if not (payload.get("URL") or "").strip():
        return jsonify({"ok": False, "error": "La URL es obligatoria"}), 400
    try:
        row_id = create_link(payload)
        return jsonify({"ok": True, "row_id": row_id})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/links/<int:row_id>", methods=["PUT"])
def update_link_route(row_id):
    payload = request.get_json(force=True)
    try:
        update_link(row_id, payload)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/links/<int:row_id>", methods=["DELETE"])
def delete_link_route(row_id):
    try:
        delete_link(row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/documentos", methods=["GET"])
def get_documentos():
    try:
        return jsonify({"ok": True, "data": read_file_records(DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS)})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/documentos", methods=["POST"])
def upload_documento():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No se recibió ningún archivo"}), 400
    extra = {
        "Comentario": (request.form.get("Comentario") or "").strip(),
        "Proyecto vinculado": (request.form.get("Proyecto vinculado") or "").strip(),
        "Tipo de Documento": (request.form.get("Tipo de Documento") or "").strip(),
        "Autor": (request.form.get("Autor") or "").strip(),
    }
    try:
        row_id = create_file_record(DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS, DOCS_DIR, file, extra)
        return jsonify({"ok": True, "row_id": row_id})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/documentos/<int:row_id>/descargar", methods=["GET"])
def download_documento(row_id):
    record = get_file_record(DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS, row_id)
    if not record or not record.get("Archivo"):
        return jsonify({"ok": False, "error": "No encontrado"}), 404
    file_path = os.path.join(DOCS_DIR, record["Archivo"])
    if not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "El archivo ya no existe en disco"}), 404
    return send_file(file_path, as_attachment=True, download_name=record.get("Nombre") or record["Archivo"])


@app.route("/api/documentos/<int:row_id>", methods=["DELETE"])
def delete_documento_route(row_id):
    try:
        delete_file_record(DOCUMENTOS_SHEET, DOCUMENTOS_COLUMNS, DOCS_DIR, row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/diagramas", methods=["GET"])
def get_diagramas():
    try:
        return jsonify({"ok": True, "data": read_file_records(DIAGRAMAS_SHEET, DIAGRAMAS_COLUMNS)})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/diagramas", methods=["POST"])
def upload_diagrama():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No se recibió ningún archivo"}), 400
    extra = {
        "Comentario": (request.form.get("Comentario") or "").strip(),
        "Autor": (request.form.get("Autor") or "").strip(),
    }
    try:
        row_id = create_file_record(DIAGRAMAS_SHEET, DIAGRAMAS_COLUMNS, DIAGRAMS_DIR, file, extra)
        return jsonify({"ok": True, "row_id": row_id})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/diagramas/<int:row_id>/descargar", methods=["GET"])
def download_diagrama(row_id):
    record = get_file_record(DIAGRAMAS_SHEET, DIAGRAMAS_COLUMNS, row_id)
    if not record or not record.get("Archivo"):
        return jsonify({"ok": False, "error": "No encontrado"}), 404
    file_path = os.path.join(DIAGRAMS_DIR, record["Archivo"])
    if not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "El archivo ya no existe en disco"}), 404
    return send_file(file_path, as_attachment=True, download_name=record.get("Nombre") or record["Archivo"])


@app.route("/api/diagramas/<int:row_id>", methods=["DELETE"])
def delete_diagrama_route(row_id):
    try:
        delete_file_record(DIAGRAMAS_SHEET, DIAGRAMAS_COLUMNS, DIAGRAMS_DIR, row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/proyectos", methods=["GET"])
def get_proyectos():
    try:
        return jsonify({"ok": True, "data": read_proyectos()})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/proyectos", methods=["POST"])
def create_proyecto_route():
    payload = request.get_json(force=True)
    try:
        row_id = create_proyecto(payload)
        return jsonify({"ok": True, "row_id": row_id})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/proyectos/<int:row_id>", methods=["PUT"])
def update_proyecto_route(row_id):
    payload = request.get_json(force=True)
    try:
        result = update_proyecto(row_id, payload)
        return jsonify({"ok": True, **result})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/proyectos/<int:row_id>", methods=["DELETE"])
def delete_proyecto_route(row_id):
    try:
        delete_proyecto(row_id)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/roadmap", methods=["GET"])
def get_roadmap():
    try:
        return jsonify({"ok": True, "data": read_roadmap()})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/roadmap/task/<int:row_id>/move", methods=["POST"])
def move_roadmap_task_route(row_id):
    payload = request.get_json(force=True)
    direction = payload.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "error": "Dirección inválida"}), 400
    try:
        move_roadmap_task(row_id, direction)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/listas", methods=["GET"])
def get_listas():
    try:
        return jsonify({"ok": True, "data": read_listas()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/listas/<path:column_name>", methods=["POST"])
def create_lista_item(column_name):
    payload = request.get_json(force=True)
    value = (payload.get("value") or "").strip()
    if not value:
        return jsonify({"ok": False, "error": "El valor no puede estar vacío"}), 400
    try:
        add_lista_item(column_name, value)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/listas/<path:column_name>", methods=["PUT"])
def rename_lista_item_route(column_name):
    payload = request.get_json(force=True)
    old_value = (payload.get("old_value") or "").strip()
    new_value = (payload.get("new_value") or "").strip()
    cascade = bool(payload.get("cascade", True))
    if not old_value or not new_value:
        return jsonify({"ok": False, "error": "Faltan datos para renombrar"}), 400
    try:
        result = rename_lista_item(column_name, old_value, new_value, cascade)
        return jsonify({"ok": True, **result})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/listas/<path:column_name>", methods=["DELETE"])
def delete_lista_item_route(column_name):
    payload = request.get_json(force=True)
    value = (payload.get("value") or "").strip()
    if not value:
        return jsonify({"ok": False, "error": "Falta el valor a eliminar"}), 400
    try:
        delete_lista_item(column_name, value)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion", methods=["GET"])
def get_planificacion():
    try:
        return jsonify({"ok": True, "data": read_planificacion()})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "No se encontró el archivo Excel en data/"}), 404
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/cell", methods=["PUT"])
def update_planificacion_cell():
    payload = request.get_json(force=True)
    try:
        row = int(payload["row"])
        col = int(payload["col"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "Fila/columna inválida"}), 400
    active = bool(payload.get("active", True))
    label = payload.get("label") or ""
    color = payload.get("color") or PLANIFICACION_DEFAULT_COLOR
    try:
        write_planificacion_cell(row, col, active, label, color)
        return jsonify({"ok": True})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/cells", methods=["PUT"])
def update_planificacion_cells_batch():
    payload = request.get_json(force=True)
    raw_cells = payload.get("cells") or []
    try:
        cells = [(int(c["row"]), int(c["col"])) for c in raw_cells]
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "Celdas inválidas"}), 400
    if not cells:
        return jsonify({"ok": False, "error": "No se seleccionaron celdas"}), 400
    active = bool(payload.get("active", True))
    label = payload.get("label") or ""
    color = payload.get("color") or PLANIFICACION_DEFAULT_COLOR
    try:
        write_planificacion_cells_batch(cells, active, label, color)
        return jsonify({"ok": True, "count": len(cells)})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/section", methods=["POST"])
def create_planificacion_section():
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "El nombre del proyecto no puede estar vacío"}), 400
    try:
        row = add_planificacion_section(name)
        return jsonify({"ok": True, "row": row})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/task", methods=["POST"])
def create_planificacion_task():
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    notas = (payload.get("notas") or "").strip()
    try:
        section_row = int(payload["section_row"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "Proyecto inválido"}), 400
    if not name:
        return jsonify({"ok": False, "error": "El nombre de la tarea no puede estar vacío"}), 400
    try:
        row = add_planificacion_task(section_row, name, notas)
        return jsonify({"ok": True, "row": row})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/week/<int:col>", methods=["PUT"])
def update_planificacion_week_route(col):
    payload = request.get_json(force=True)
    month = payload.get("month")
    week = payload.get("week")
    if month is not None:
        month = month.strip()
    if week is not None:
        week = week.strip()
    try:
        update_planificacion_week(col, month, week)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/week/<int:col>", methods=["DELETE"])
def delete_planificacion_week_route(col):
    try:
        delete_planificacion_week(col)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/month", methods=["POST"])
def create_planificacion_month():
    payload = request.get_json(force=True)
    month_name = (payload.get("month_name") or "").strip()
    try:
        num_weeks = int(payload.get("num_weeks", 4))
    except (TypeError, ValueError):
        num_weeks = 4
    num_weeks = max(1, min(num_weeks, 6))
    if not month_name:
        return jsonify({"ok": False, "error": "El nombre del mes no puede estar vacío"}), 400
    try:
        start_col = add_planificacion_month(month_name, num_weeks)
        return jsonify({"ok": True, "start_col": start_col})
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/task/<int:row>", methods=["PUT"])
def update_planificacion_task_route(row):
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    notas = (payload.get("notas") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "El nombre de la tarea no puede estar vacío"}), 400
    try:
        update_planificacion_task(row, name, notas)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/section/<int:row>", methods=["PUT"])
def update_planificacion_section_route(row):
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "El nombre del proyecto no puede estar vacío"}), 400
    try:
        update_planificacion_section(row, name)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/task/<int:row>/move", methods=["POST"])
def move_planificacion_task_route(row):
    payload = request.get_json(force=True)
    direction = payload.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"ok": False, "error": "Dirección inválida"}), 400
    try:
        new_row = move_planificacion_task(row, direction)
        return jsonify({"ok": True, "row": new_row})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/task/<int:row>", methods=["DELETE"])
def delete_planificacion_task_route(row):
    try:
        delete_planificacion_task(row)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/section/<int:row>", methods=["DELETE"])
def delete_planificacion_section_route(row):
    try:
        delete_planificacion_section(row)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/planificacion/month", methods=["DELETE"])
def delete_planificacion_month_route():
    payload = request.get_json(force=True)
    month_name = (payload.get("month_name") or "").strip()
    if not month_name:
        return jsonify({"ok": False, "error": "Falta el nombre del mes"}), 400
    try:
        delete_planificacion_month(month_name)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except PermissionError:
        return jsonify({"ok": False, "error": "El archivo Excel está abierto en otro programa. Ciérralo e intenta de nuevo."}), 423
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def supabase_upload(path_in_bucket, file_bytes, content_type="application/octet-stream"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "Falta configurar SUPABASE_URL y SUPABASE_SERVICE_KEY en el archivo .env del proyecto."
        )
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path_in_bucket}"
    req = urllib.request.Request(url, data=file_bytes, method="POST")
    req.add_header("apikey", SUPABASE_SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    req.add_header("Content-Type", content_type)
    req.add_header("x-upsert", "true")  # sobrescribe si ya existe, en vez de fallar
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Supabase respondió {e.code}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a Supabase: {e.reason}")


def supabase_list(prefix):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Falta configurar SUPABASE_URL y SUPABASE_SERVICE_KEY en el archivo .env del proyecto.")
    url = f"{SUPABASE_URL}/storage/v1/object/list/{SUPABASE_BUCKET}"
    body = json.dumps({"prefix": prefix, "limit": 1000, "offset": 0}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("apikey", SUPABASE_SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase respondió {e.code}: {e.read().decode('utf-8', errors='ignore')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a Supabase: {e.reason}")


def supabase_delete(paths):
    if not paths:
        return
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Falta configurar SUPABASE_URL y SUPABASE_SERVICE_KEY en el archivo .env del proyecto.")
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}"
    body = json.dumps({"prefixes": paths}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="DELETE")
    req.add_header("apikey", SUPABASE_SERVICE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase respondió {e.code}: {e.read().decode('utf-8', errors='ignore')}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo conectar a Supabase: {e.reason}")


@app.route("/api/backup/supabase", methods=["GET"])
def backup_supabase_status():
    return jsonify({
        "ok": True,
        "configured": bool(SUPABASE_URL and SUPABASE_SERVICE_KEY),
        "bucket": SUPABASE_BUCKET,
    })


@app.route("/api/backup/supabase", methods=["POST"])
def backup_to_supabase():
    try:
        subidos = []

        with open(EXCEL_PATH, "rb") as f:
            excel_bytes = f.read()
        excel_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        # Un único archivo fijo que se sobrescribe cada vez (x-upsert): así el
        # respaldo no acumula una copia nueva por cada clic.
        supabase_upload("excel/Seguimiento_y_planificacion.xlsx", excel_bytes, excel_mime)
        subidos.append("Excel")

        for folder, prefix in ((DOCS_DIR, "documentos"), (DIAGRAMS_DIR, "diagramas")):
            if os.path.isdir(folder):
                archivos = [n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))]
                for nombre in archivos:
                    with open(os.path.join(folder, nombre), "rb") as f:
                        supabase_upload(f"{prefix}/{nombre}", f.read())
                if archivos:
                    subidos.append(f"{len(archivos)} archivo(s) de {prefix}")

        return jsonify({"ok": True, "uploaded": subidos, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/backup/supabase/limpiar", methods=["POST"])
def limpiar_respaldos_antiguos():
    """Elimina los respaldos de Excel con marca de tiempo que quedaron de versiones
    anteriores de esta función (antes de que el respaldo pasara a sobrescribir un
    único archivo fijo)."""
    try:
        objetos = supabase_list("excel")
        a_borrar = [
            f"excel/{o['name']}" for o in objetos
            if o.get("name") and o["name"] != "Seguimiento_y_planificacion.xlsx"
        ]
        if a_borrar:
            supabase_delete(a_borrar)
        return jsonify({"ok": True, "deleted": len(a_borrar)})
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/export", methods=["GET"])
def export_excel():
    return send_file(EXCEL_PATH, as_attachment=True,
                      download_name="Seguimiento_y_planificacion.xlsx")


@app.route("/")
def index():
    return render_template("index.html")


# Corre siempre al importar el módulo (no solo cuando se ejecuta directo),
# para que la auto-migración de esquema funcione sin importar cómo se
# levante la app (python app.py, gunicorn, etc.)
ensure_schema()

if __name__ == "__main__":
    if not os.path.exists(EXCEL_PATH):
        print(f"⚠️  No se encontró el archivo en {EXCEL_PATH}")
        print("Copia tu Excel ahí con el nombre 'Seguimiento_y_planificacion.xlsx' o edita EXCEL_PATH en app.py")
    print("\n🚀 Abre tu navegador en: http://127.0.0.1:5050\n")
    app.run(debug=True, port=5050)
