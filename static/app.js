const state = {
  tareas: [],
  listas: {},
  proyectos: [],
  roadmapData: null,
  roadmapYear: new Date().getFullYear(),
  planificacion: null,
  pasosProd: [],
  incidencias: [],
  incidenciaEstados: [],
  incidenciaEstadoColors: {},
  links: [],
  documentos: [],
  diagramas: [],
  docSub: "links",
  incidenciaFilters: { estado: "", responsableSeguimiento: "", responsableDesarrollo: "" },
  incidenciaSort: { column: "Prioridad", dir: "asc" },
  planCollapsed: new Set(),
  filters: { proyecto: "", estado: "", prioridad: "", responsable: "", search: "" },
  view: "tabla",
  editingRowId: null,
};

const el = (id) => document.getElementById(id);

function slug(s) {
  return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, "-");
}

function showToast(msg, isError = false) {
  const t = el("toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => (t.className = "toast"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || "Error de red");
  }
  return data;
}

/* =========================================================================
   Generic modal system (replaces browser prompt()/confirm())
   ========================================================================= */

const PLAN_COLORS = [
  { name: "Amarillo", hex: "#FFEB3B" },
  { name: "Naranja", hex: "#FFA726" },
  { name: "Rojo", hex: "#EF5350" },
  { name: "Rosa", hex: "#EC407A" },
  { name: "Morado", hex: "#AB47BC" },
  { name: "Azul", hex: "#42A5F5" },
  { name: "Turquesa", hex: "#26C6DA" },
  { name: "Verde", hex: "#66BB6A" },
  { name: "Gris", hex: "#90A4AE" },
  { name: "Ámbar (default)", hex: "#F2A93B" },
];

/* ---------- Combobox: dropdown que se abre completo con un clic ----------
   Reemplaza el <input list> + <datalist> nativo, que en varios navegadores no
   vuelve a mostrar sugerencias si el input ya tiene un valor que calza
   exactamente con una opción (hay que borrar primero). Este componente
   siempre muestra la lista completa al hacer foco/clic, y filtra en vivo
   mientras se escribe. */
function attachCombobox(input, getOptions, opts = {}) {
  if (!input || input.dataset.comboAttached) return;
  input.dataset.comboAttached = "1";
  const strict = !!opts.strict;

  let wrap = input.parentElement;
  if (!wrap.classList.contains("combo-wrap") && !wrap.classList.contains("plan-combo-wrap")) {
    wrap = document.createElement("div");
    wrap.className = "plan-combo-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
  }
  let panel = wrap.querySelector(".combo-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "combo-panel";
    wrap.appendChild(panel);
  }

  function renderOptions(filterText) {
    const options = getOptions() || [];
    const q = (filterText || "").toLowerCase();
    const filtered = q ? options.filter((o) => o.toLowerCase().includes(q)) : options;
    if (!filtered.length) {
      panel.innerHTML = `<div class="combo-empty">Sin coincidencias</div>`;
      return;
    }
    panel.innerHTML = filtered
      .map((o) => `<div class="combo-option" data-value="${o.replace(/"/g, "&quot;")}">${o}</div>`)
      .join("");
    panel.querySelectorAll(".combo-option").forEach((opt) => {
      opt.addEventListener("mousedown", (e) => {
        e.preventDefault();
        input.value = opt.dataset.value;
        closePanel();
        input.dispatchEvent(new Event("change"));
      });
    });
  }

  function openPanel() {
    renderOptions(""); // clic => siempre la lista completa, sin importar el valor actual
    panel.classList.add("open");
  }
  function closePanel() {
    panel.classList.remove("open");
  }
  function enforceStrictValue() {
    if (!strict) return;
    const options = getOptions() || [];
    const current = input.value.trim();
    if (current && !options.includes(current)) {
      input.value = "";
      showToast("Solo se permiten valores de la lista. Elige uno de las opciones.", true);
      input.dispatchEvent(new Event("change"));
    }
  }

  input.addEventListener("focus", openPanel);
  input.addEventListener("click", openPanel);
  input.addEventListener("input", () => {
    renderOptions(input.value);
    panel.classList.add("open");
  });
  input.addEventListener("blur", () => {
    enforceStrictValue();
    setTimeout(closePanel, 120);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanel();
  });
}

let _formModalResolve = null;

function openPlanFormModal({ title, fields, submitLabel = "Guardar", onDelete = null, deleteLabel = "Eliminar" }) {
  return new Promise((resolve) => {
    _formModalResolve = resolve;
    el("plan-modal-title").textContent = title;
    el("plan-modal-submit-btn").textContent = submitLabel;

    const body = el("plan-modal-body");
    body.innerHTML = fields
      .map((f) => {
        if (f.type === "checkbox") {
          return `<div class="plan-field-group plan-field-checkbox-group">
            <label class="plan-checkbox-label">
              <input type="checkbox" id="pf-${f.name}" ${f.value ? "checked" : ""}>
              ${f.label}
            </label>
            ${f.hint ? `<p class="plan-field-hint">${f.hint}</p>` : ""}
          </div>`;
        }
        if (f.type === "select") {
          const optsHtml = (f.options || [])
            .map((o) => `<option value="${o}" ${o === f.value ? "selected" : ""}>${o}</option>`)
            .join("");
          const dotHtml = f.colorMap ? `<span class="estado-color-dot" id="pf-${f.name}-dot"></span>` : "";
          return `<div class="plan-field-group">
            <label for="pf-${f.name}">${f.label}</label>
            <div class="pf-select-row">${dotHtml}<select id="pf-${f.name}">${optsHtml}</select></div>
            ${f.hint ? `<p class="plan-field-hint">${f.hint}</p>` : ""}
          </div>`;
        }
        if (f.type === "combo") {
          const val = (f.value ?? "").toString().replace(/"/g, "&quot;");
          return `<div class="plan-field-group">
            <label for="pf-${f.name}">${f.label}</label>
            <div class="plan-combo-wrap">
              <input type="text" id="pf-${f.name}" class="combo-input" autocomplete="off" value="${val}" placeholder="${f.placeholder || ""}">
            </div>
            ${f.hint ? `<p class="plan-field-hint">${f.hint}</p>` : ""}
          </div>`;
        }
        const tag = f.type === "textarea" ? "textarea" : "input";
        const typeAttr = f.type === "textarea" ? "" : `type="${f.type || "text"}"`;
        const extra = f.type === "number" ? `min="${f.min ?? 1}" max="${f.max ?? 99}"` : "";
        const rows = f.type === "textarea" ? `rows="${f.rows || 2}"` : "";
        const cls = f.mono ? `class="mono-textarea"` : "";
        const val = (f.value ?? "").toString().replace(/"/g, "&quot;");
        return `<div class="plan-field-group">
          <label for="pf-${f.name}">${f.label}</label>
          <${tag} id="pf-${f.name}" ${typeAttr} ${extra} ${rows} ${cls} placeholder="${f.placeholder || ""}" ${
          f.type === "textarea" ? `>${val}</textarea>` : `value="${val}">`
        }
          ${f.hint ? `<p class="plan-field-hint">${f.hint}</p>` : ""}
        </div>`;
      })
      .join("");

    fields.forEach((f) => {
      if (f.type === "combo") {
        attachCombobox(el(`pf-${f.name}`), () => f.options || [], { strict: !!f.strict });
      }
      if (f.type === "select" && f.colorMap) {
        const selectEl = el(`pf-${f.name}`);
        const dot = el(`pf-${f.name}-dot`);
        const updateDot = () => (dot.style.background = f.colorMap[selectEl.value] || "#ccc");
        selectEl.addEventListener("change", updateDot);
        updateDot();
      }
    });

    const delBtn = el("plan-modal-delete-btn");
    if (onDelete) {
      delBtn.style.display = "inline-block";
      delBtn.textContent = deleteLabel;
      delBtn.onclick = () => {
        closePlanFormModal(null);
        onDelete();
      };
    } else {
      delBtn.style.display = "none";
      delBtn.onclick = null;
    }

    el("plan-modal-overlay").classList.add("active");
    const firstInput = body.querySelector("input, textarea");
    if (firstInput) setTimeout(() => firstInput.focus(), 50);

    el("plan-modal-submit-btn").onclick = () => {
      const values = {};
      fields.forEach((f) => {
        const elm = el(`pf-${f.name}`);
        values[f.name] = f.type === "checkbox" ? elm.checked : elm.value.trim();
      });
      closePlanFormModal(values);
    };
  });
}

function closePlanFormModal(result) {
  el("plan-modal-overlay").classList.remove("active");
  if (_formModalResolve) {
    _formModalResolve(result);
    _formModalResolve = null;
  }
}

let _confirmModalResolve = null;

function openConfirmModal({ title = "¿Confirmar?", message, confirmLabel = "Eliminar" }) {
  return new Promise((resolve) => {
    _confirmModalResolve = resolve;
    el("confirm-modal-title").textContent = title;
    el("confirm-modal-message").textContent = message;
    el("confirm-modal-ok-btn").textContent = confirmLabel;
    el("confirm-modal-ok-btn").onclick = () => closeConfirmModal(true);
    el("confirm-modal-overlay").classList.add("active");
  });
}

function closeConfirmModal(result) {
  el("confirm-modal-overlay").classList.remove("active");
  if (_confirmModalResolve) {
    _confirmModalResolve(result);
    _confirmModalResolve = null;
  }
}

let _cellModalResolve = null;

function openCellModal({ title = "Editar semana", label = "", color = "" }) {
  return new Promise((resolve) => {
    _cellModalResolve = resolve;
    el("cell-modal-title").textContent = title;
    el("cell-modal-label-input").value = label || "";

    let selectedColor = color || PLAN_COLORS[PLAN_COLORS.length - 1].hex;
    const grid = el("cell-modal-swatches");
    grid.innerHTML = PLAN_COLORS.map(
      (c) => `<div class="color-swatch${c.hex.toUpperCase() === selectedColor.toUpperCase() ? " selected" : ""}"
                   style="background:${c.hex}" title="${c.name}" data-hex="${c.hex}"></div>`
    ).join("");
    grid.querySelectorAll(".color-swatch").forEach((sw) => {
      sw.addEventListener("click", () => {
        selectedColor = sw.dataset.hex;
        grid.querySelectorAll(".color-swatch").forEach((s) => s.classList.remove("selected"));
        sw.classList.add("selected");
      });
    });

    el("cell-modal-overlay").classList.add("active");
    setTimeout(() => el("cell-modal-label-input").focus(), 50);

    el("cell-modal-save-btn").onclick = () => {
      closeCellModal({ action: "save", label: el("cell-modal-label-input").value.trim(), color: selectedColor });
    };
    el("cell-modal-clear-btn").onclick = () => {
      closeCellModal({ action: "clear" });
    };
  });
}

function closeCellModal(result) {
  el("cell-modal-overlay").classList.remove("active");
  if (_cellModalResolve) {
    _cellModalResolve(result);
    _cellModalResolve = null;
  }
}

async function loadAll() {
  try {
    const [tareasRes, listasRes, pasosRes, incidenciasRes, linksRes, documentosRes, diagramasRes, proyectosRes] = await Promise.all([
      api("/api/tareas"),
      api("/api/listas"),
      api("/api/pasos-prod"),
      api("/api/incidencias"),
      api("/api/links"),
      api("/api/documentos"),
      api("/api/diagramas"),
      api("/api/proyectos"),
    ]);
    state.tareas = tareasRes.data;
    state.listas = listasRes.data;
    state.pasosProd = pasosRes.data;
    state.incidencias = incidenciasRes.data;
    state.incidenciaEstados = incidenciasRes.estados || [];
    state.incidenciaEstadoColors = incidenciasRes.estado_colors || {};
    state.links = linksRes.data;
    state.documentos = documentosRes.data;
    state.diagramas = diagramasRes.data;
    state.proyectos = proyectosRes.data;
    el("file-status").textContent = `${state.tareas.length} tareas · sincronizado con el Excel`;
    populateFilterOptions();
    render();
  } catch (e) {
    el("file-status").textContent = "Error al cargar el archivo";
    showToast(e.message, true);
  }
}

function proyectoNombres() {
  return state.proyectos.map((p) => p.Nombre);
}

function populateFilterOptions() {
  const proyectos = [...new Set(state.tareas.map((t) => t.Proyecto).filter(Boolean))].sort();
  const estados = [...new Set(state.tareas.map((t) => t.Estado).filter(Boolean))].sort();
  const prioridades = [...new Set(state.tareas.map((t) => t.Prioridad).filter(Boolean))].sort();
  const responsables = [...new Set(state.tareas.map((t) => t.Responsable).filter(Boolean))].sort();

  fillSelect("f-proyecto", proyectos, "Todos los proyectos");
  fillSelect("f-estado", estados, "Todos los estados");
  fillSelect("f-prioridad", prioridades, "Todas las prioridades");
  fillSelect("f-responsable", responsables, "Todos los responsables");

  fillDatalist("dl-proyecto", proyectoNombres());

  const incidenciaRespSeguimiento = [...new Set(state.incidencias.map((i) => i["Responsable (seguimiento)"]).filter(Boolean))].sort();
  const incidenciaRespDesarrollo = [...new Set(state.incidencias.map((i) => i["Responsable (desarrollo)"]).filter(Boolean))].sort();
  fillSelect("f-incidencia-estado", state.incidenciaEstados, "Todos los estados");
  fillSelect("f-incidencia-responsable-seguimiento", incidenciaRespSeguimiento, "Todos (seguimiento)");
  fillSelect("f-incidencia-responsable-desarrollo", incidenciaRespDesarrollo, "Todos (desarrollo)");
}

function fillSelect(id, values, placeholder) {
  const sel = el(id);
  const current = sel.value;
  sel.innerHTML = `<option value="">${placeholder}</option>` + values.map((v) => `<option value="${v}">${v}</option>`).join("");
  sel.value = current;
}

function fillDatalist(id, values) {
  el(id).innerHTML = values.map((v) => `<option value="${v}">`).join("");
}

function getFiltered() {
  const f = state.filters;
  return state.tareas.filter((t) => {
    if (f.proyecto && t.Proyecto !== f.proyecto) return false;
    if (f.estado && t.Estado !== f.estado) return false;
    if (f.prioridad && t.Prioridad !== f.prioridad) return false;
    if (f.responsable && t.Responsable !== f.responsable) return false;
    if (f.search) {
      const hay = `${t.Tarea || ""} ${t.Subtarea || ""} ${t.Notas || ""}`.toLowerCase();
      if (!hay.includes(f.search.toLowerCase())) return false;
    }
    return true;
  });
}

function render() {
  renderStats();
  if (state.view === "tabla") renderTable();
  else if (state.view === "kanban") renderKanban();
  else if (state.view === "planificacion") renderRoadmap();
  else if (state.view === "equipo") { renderEquipo(); renderProyectos(); }
  else if (state.view === "pasosprod") renderPasosProd();
  else if (state.view === "incidencias") renderIncidencias();
  else if (state.view === "documentacion") renderDocumentacion();
}

function renderStats() {
  const t = state.tareas;
  const enCurso = t.filter((x) => x.Estado === "En curso").length;
  const sinIniciar = t.filter((x) => x.Estado === "Sin iniciar").length;
  const completado = t.filter((x) => x.Estado === "Completado").length;
  const alta = t.filter((x) => x.Prioridad === "Alta" || x.Prioridad === "Urgente").length;

  el("stats-row").innerHTML = `
    <div class="stat-card"><div class="stat-value">${t.length}</div><div class="stat-label">Total tareas</div></div>
    <div class="stat-card"><div class="stat-value">${enCurso}</div><div class="stat-label">En curso</div></div>
    <div class="stat-card"><div class="stat-value">${sinIniciar}</div><div class="stat-label">Sin iniciar</div></div>
    <div class="stat-card"><div class="stat-value">${completado}</div><div class="stat-label">Completadas</div></div>
    <div class="stat-card"><div class="stat-value">${alta}</div><div class="stat-label">Alta / urgente</div></div>
  `;
}

function badge(kind, value) {
  if (!value) return "";
  return `<span class="badge badge-${kind}-${slug(value)}">${value}</span>`;
}

function renderTable() {
  const rows = getFiltered();
  el("empty-state").style.display = rows.length ? "none" : "block";
  el("tabla-body").innerHTML = rows
    .map(
      (t) => `
    <tr data-row-id="${t.row_id}">
      <td>${t.Proyecto || ""}</td>
      <td class="cell-tarea">${t.Tarea || ""}</td>
      <td class="cell-sub">${t.Subtarea || ""}</td>
      <td>${t.Responsable || ""}</td>
      <td>${badge("estado", t.Estado)}</td>
      <td>${badge("prioridad", t.Prioridad)}</td>
      <td>
        <div class="progress-wrap">
          <div class="progress-track"><div class="progress-fill" style="width:${t["% Avance"] || 0}%"></div></div>
          <span class="progress-text">${t["% Avance"] || 0}%</span>
        </div>
      </td>
      <td>${t["Fecha Inicio"] || ""}</td>
      <td>${t["Fecha Fin"] || ""}</td>
      <td>${t["Horas Estimadas"] || ""}</td>
      <td>${t["Horas Reales"] || ""}</td>
      <td class="cell-notas"><span class="notas-clamp">${t.Notas || ""}</span></td>
      <td><button class="icon-btn" onclick="event.stopPropagation(); openEdit(${t.row_id})">✎</button>${noteBubbleIcon(t.Log, { title: "Ver log", icon: "🧾", onclick: `viewTareaLog(${t.row_id})` })}</td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#tabla-body tr").forEach((tr) => {
    tr.addEventListener("click", () => openEdit(Number(tr.dataset.rowId)));
  });
}

function renderKanban() {
  const rows = getFiltered();
  const cols = ["Sin iniciar", "En curso", "Bloqueado", "Completado", "Permanente"];
  const present = [...new Set(rows.map((r) => r.Estado).filter(Boolean))];
  const order = cols.filter((c) => present.includes(c)).concat(present.filter((c) => !cols.includes(c)));
  const finalCols = order.length ? order : cols;

  el("kanban-board").innerHTML = finalCols
    .map((estado) => {
      const items = rows.filter((r) => r.Estado === estado);
      return `
      <div class="kanban-col">
        <div class="kanban-col-header">${estado} <span class="kanban-count">${items.length}</span></div>
        ${items
          .map(
            (t) => `
          <div class="kanban-card pri-${slug(t.Prioridad)}" onclick="openEdit(${t.row_id})">
            <div class="kanban-card-title">${t.Tarea || ""}${t.Subtarea ? " · " + t.Subtarea : ""}</div>
            <div class="kanban-card-meta"><span>${t.Responsable || "—"}</span><span>${t["% Avance"] || 0}%</span></div>
          </div>`
          )
          .join("")}
      </div>`;
    })
    .join("");
}

/* ---------- Planificacion (Gantt) ---------- */

function viewTareaNotaRoadmap(rowId) {
  const t = state.tareas.find((x) => x.row_id === rowId);
  if (!t) return;
  openTextViewerModal(t.Tarea || "Tarea", t.Notas || "");
}

/* ---------- Roadmap (Gantt anual por proyecto) ---------- */

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

async function loadRoadmap() {
  try {
    const res = await api("/api/roadmap");
    state.roadmapData = res.data;
  } catch (e) {
    showToast(e.message, true);
    state.roadmapData = { proyectos: [], sin_fecha: [] };
  }
}

function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

function monthsSpan(fechaInicio, fechaFin, year) {
  // Convierte un rango de fechas (YYYY-MM-DD) a columnas de mes (0-11), recortadas al año
  // visible, más la posición exacta del día dentro del mes de inicio/fin (0 a 1) para que
  // la barra no ocupe el mes completo si la fecha real cae a mitad de mes.
  const ini = new Date(fechaInicio + "T00:00:00");
  const fin = new Date(fechaFin + "T00:00:00");
  const anioInicio = new Date(year, 0, 1);
  const anioFin = new Date(year, 11, 31);
  if (fin < anioInicio || ini > anioFin) return null;
  const iniClip = ini < anioInicio ? anioInicio : ini;
  const finClip = fin > anioFin ? anioFin : fin;

  const colInicio = iniClip.getMonth();
  const colFin = finClip.getMonth();
  const startFrac = (iniClip.getDate() - 1) / daysInMonth(iniClip.getFullYear(), colInicio);
  const endFrac = finClip.getDate() / daysInMonth(finClip.getFullYear(), colFin);

  return { colInicio, colFin, startFrac, endFrac };
}

function barPosition(colInicio, colFin, startFrac, endFrac) {
  // left/width expresados en "anchos de celda" (cada celda de mes = 100%), replicando la
  // convención previa (barra completa = N*100% + (N-1)px de bordes) pero con offsets
  // fraccionarios de día dentro del mes de inicio y de fin.
  let spanFrac, borderPx;
  if (colInicio === colFin) {
    spanFrac = endFrac - startFrac;
    borderPx = 0;
  } else {
    spanFrac = (1 - startFrac) + (colFin - colInicio - 1) + endFrac;
    borderPx = colFin - colInicio;
  }
  return {
    left: `calc(${startFrac * 100}% + 2px)`,
    width: `calc(${spanFrac * 100}% + ${borderPx}px)`,
  };
}

function renderRoadmap() {
  if (!state.roadmapData) {
    el("roadmap-gantt").innerHTML = `<div class="estado-vacio">Cargando…</div>`;
    loadRoadmap().then(renderRoadmap);
    return;
  }

  const year = state.roadmapYear;
  el("roadmap-year-label").textContent = year;

  const { proyectos, sin_fecha } = state.roadmapData;

  // Armar filas: proyecto (con su rango, "estimado") + sus tareas clave (hijas, rango real)
  const filas = [];
  proyectos.forEach((p) => {
    const rangoProyecto = p["Fecha Inicio"] && p["Fecha Fin"] ? monthsSpan(p["Fecha Inicio"], p["Fecha Fin"], year) : null;
    const hijos = [];
    p.tareas.forEach((t) => {
      const rango = monthsSpan(t["Fecha Inicio"], t["Fecha Fin"], year);
      if (!rango) return; // la tarea tiene fecha pero cae fuera del año visible
      hijos.push({
        id: `t-${t.row_id}`,
        label: t.label,
        colorHex: p.Color,
        colInicio: rango.colInicio,
        colFin: rango.colFin,
        startFrac: rango.startFrac,
        endFrac: rango.endFrac,
        comentario: t.Notas,
        onClick: () => openEdit(t.row_id),
      });
    });
    filas.push({
      id: `p-${p.row_id}`,
      label: p.Nombre,
      colorHex: p.Color,
      colInicio: rangoProyecto ? rangoProyecto.colInicio : null,
      colFin: rangoProyecto ? rangoProyecto.colFin : null,
      startFrac: rangoProyecto ? rangoProyecto.startFrac : null,
      endFrac: rangoProyecto ? rangoProyecto.endFrac : null,
      estimado: true,
      hijos,
      onClick: () => editProyecto(p.row_id),
    });
  });

  const hayAlgoQueMostrar = filas.some((f) => f.colInicio !== null || f.hijos.length);
  if (!hayAlgoQueMostrar) {
    el("roadmap-gantt").innerHTML = `<div class="estado-vacio">Ningún proyecto o tarea clave tiene fechas dentro de ${year}. Usa las flechas para cambiar de año, o asigna fechas estimadas a un proyecto en "Equipo y Proyectos".</div>`;
  } else {
    let html = `<div class="cal-grid"><div class="cal-corner">Proyecto</div>`;
    MESES.forEach((m, i) => (html += `<div class="cal-head ${i % 3 === 0 ? "q-start" : ""}">${m}</div>`));

    filas.forEach((fila) => {
      const tieneHijos = fila.hijos.length > 0;
      const contraido = state.planCollapsed.has(fila.id);
      html += `<div class="cal-row-label">
        ${tieneHijos ? `<button class="cal-row-toggle" onclick="toggleRoadmapRow('${fila.id}')">${contraido ? "▸" : "▾"}</button>` : ""}
        <span onclick="editProyecto(${fila.id.split("-")[1]})" style="cursor:pointer">${fila.label}</span>
      </div>`;
      for (let i = 0; i < 12; i++) {
        html += `<div class="cal-cell ${i % 3 === 0 ? "q-start" : ""}">`;
        if (fila.colInicio !== null && i === fila.colInicio) {
          const pos = barPosition(fila.colInicio, fila.colFin, fila.startFrac, fila.endFrac);
          html += `<div class="cal-bar estimado" style="background:${fila.colorHex}; left:${pos.left}; width:${pos.width}" title="${fila.label} (estimado)" onclick="editProyecto(${fila.id.split("-")[1]})">${fila.label}</div>`;
        }
        html += `</div>`;
      }

      if (tieneHijos && !contraido) {
        fila.hijos.forEach((hijo) => {
          html += `<div class="cal-row-label cal-row-label-hijo"><span class="cal-row-tree">└</span><span>${hijo.label}</span>${noteBubbleIcon(hijo.comentario, { title: "Ver comentario", onclick: `viewTareaNotaRoadmap(${hijo.id.split("-")[1]})` })}</div>`;
          for (let i = 0; i < 12; i++) {
            html += `<div class="cal-cell cal-cell-hijo ${i % 3 === 0 ? "q-start" : ""}">`;
            if (i === hijo.colInicio) {
              const pos = barPosition(hijo.colInicio, hijo.colFin, hijo.startFrac, hijo.endFrac);
              html += `<div class="cal-bar cal-bar-hijo" style="background:${hijo.colorHex}; left:${pos.left}; width:${pos.width}" title="${hijo.label}" onclick="openEdit(${hijo.id.split("-")[1]})">${hijo.label}</div>`;
            }
            html += `</div>`;
          }
        });
      }
    });
    html += `</div>`;
    el("roadmap-gantt").innerHTML = html;
  }

  const claveNoteBtn = el("roadmap-sin-fecha");
  if (sin_fecha && sin_fecha.length) {
    claveNoteBtn.style.display = "block";
    el("roadmap-sin-fecha-list").innerHTML = sin_fecha
      .map((s) => `<span class="chip" onclick="openEdit(${s.row_id})">${s.label} <small>(${s.proyecto})</small></span>`)
      .join("");
  } else {
    claveNoteBtn.style.display = "none";
  }
}

function toggleRoadmapRow(id) {
  if (state.planCollapsed.has(id)) state.planCollapsed.delete(id);
  else state.planCollapsed.add(id);
  renderRoadmap();
}

/* ---------- Equipo y Proyectos: gestión de Proyectos (con fechas) ---------- */

function renderProyectos() {
  const list = el("equipo-list-proyectos");
  if (!state.proyectos.length) {
    list.innerHTML = `<li class="equipo-list-empty">Sin proyectos todavía.</li>`;
    return;
  }
  list.innerHTML = state.proyectos
    .slice()
    .sort((a, b) => a.Nombre.localeCompare(b.Nombre, "es"))
    .map((p) => {
      const count = state.tareas.filter((t) => t.Proyecto === p.Nombre).length;
      const rango = p["Fecha Inicio"] && p["Fecha Fin"] ? `${p["Fecha Inicio"]} → ${p["Fecha Fin"]}` : "sin fechas estimadas";
      const oculto = p["Mostrar en Roadmap"] === "No" ? ` · <span style="color:var(--rust)">oculto del Roadmap</span>` : "";
      return `<li class="equipo-item">
        <span class="equipo-item-name">
          <span class="estado-color-dot" style="background:${p.Color}"></span>
          ${p.Nombre} <span class="equipo-item-count">${count}</span>
          <br><small style="color:var(--muted)">${rango}${oculto}</small>
        </span>
        <span class="equipo-item-actions">
          <button class="equipo-item-edit" title="Editar" onclick="editProyecto(${p.row_id})">✎</button>
          <button class="equipo-item-del" title="Eliminar" onclick="deleteProyecto(${p.row_id})">&times;</button>
        </span>
      </li>`;
    })
    .join("");
}

async function addProyecto() {
  const values = await openPlanFormModal({
    title: "Nuevo proyecto",
    submitLabel: "Agregar",
    fields: [
      { name: "Nombre", label: "Nombre del proyecto", placeholder: "ej: Checkout Rediseño" },
      { name: "Fecha Inicio", label: "Fecha inicio estimada (opcional)", type: "date" },
      { name: "Fecha Fin", label: "Fecha fin estimada (opcional)", type: "date" },
      { name: "Mostrar en Roadmap", label: "¿Deseas que este proyecto se muestre en el Roadmap?", type: "checkbox", value: true },
    ],
  });
  if (!values || !values.Nombre) return;
  values["Mostrar en Roadmap"] = values["Mostrar en Roadmap"] ? "Sí" : "No";
  try {
    await api("/api/proyectos", { method: "POST", body: JSON.stringify(values) });
    showToast(`Proyecto "${values.Nombre}" agregado`);
    await loadAll();
    state.roadmapData = null;
    renderProyectos();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editProyecto(rowId) {
  const p = state.proyectos.find((x) => x.row_id === rowId);
  if (!p) return;
  const values = await openPlanFormModal({
    title: "Editar proyecto",
    submitLabel: "Guardar",
    onDelete: () => deleteProyecto(rowId),
    fields: [
      { name: "Nombre", label: "Nombre del proyecto", value: p.Nombre },
      { name: "Fecha Inicio", label: "Fecha inicio estimada (opcional)", type: "date", value: p["Fecha Inicio"] || "" },
      { name: "Fecha Fin", label: "Fecha fin estimada (opcional)", type: "date", value: p["Fecha Fin"] || "" },
      { name: "Mostrar en Roadmap", label: "¿Deseas que este proyecto se muestre en el Roadmap?", type: "checkbox", value: p["Mostrar en Roadmap"] !== "No" },
    ],
  });
  if (!values || !values.Nombre) return;
  values["Mostrar en Roadmap"] = values["Mostrar en Roadmap"] ? "Sí" : "No";
  try {
    const res = await api(`/api/proyectos/${rowId}`, { method: "PUT", body: JSON.stringify(values) });
    showToast(res.updated_tasks ? `Actualizado en ${res.updated_tasks} tarea(s)` : "Proyecto actualizado");
    await loadAll();
    state.roadmapData = null;
    renderProyectos();
    if (state.view === "planificacion") renderRoadmap();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteProyecto(rowId) {
  const p = state.proyectos.find((x) => x.row_id === rowId);
  if (!p) return;
  const count = state.tareas.filter((t) => t.Proyecto === p.Nombre).length;
  const ok = await openConfirmModal({
    title: "Eliminar proyecto",
    message: count
      ? `"${p.Nombre}" tiene ${count} tarea(s) asociada(s). Se eliminará el proyecto, pero esas tareas conservarán el nombre (quedarán sin proyecto activo en el Roadmap). ¿Continuar?`
      : `¿Eliminar "${p.Nombre}"?`,
  });
  if (!ok) return;
  try {
    await api(`/api/proyectos/${rowId}`, { method: "DELETE" });
    showToast("Proyecto eliminado");
    await loadAll();
    state.roadmapData = null;
    renderProyectos();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Planificación (grilla semanal, LEGACY — ya no se usa desde que
   el Roadmap pasó a ser una vista derivada de Proyectos + Tareas clave) ---------- */

async function loadPlanificacion() {
  try {
    const res = await api("/api/planificacion");
    state.planificacion = res.data;
  } catch (e) {
    showToast(e.message, true);
    state.planificacion = { weeks: [], sections: [] };
  }
}

function renderPlanificacion() {
  const table = el("plan-table");
  if (!state.planificacion) {
    table.innerHTML = "<tr><td>Cargando…</td></tr>";
    loadPlanificacion().then(renderPlanificacion);
    return;
  }

  const { weeks, sections } = state.planificacion;

  // group weeks by month for the header row (colspan)
  const monthGroups = [];
  weeks.forEach((w) => {
    const last = monthGroups[monthGroups.length - 1];
    if (last && last.month === w.month) last.span += 1;
    else monthGroups.push({ month: w.month, span: 1 });
  });

  let html = "<thead>";
  html += `<tr class="plan-month-row"><th class="plan-corner"></th>${monthGroups
    .map(
      (g) =>
        `<th colspan="${g.span}">
          <span class="plan-month-label">${g.month || ""}</span>
          <button class="plan-month-del" title="Eliminar mes ${g.month || ""}" onclick="deletePlanMonth('${(g.month || "").replace(/'/g, "\\'")}')">&times;</button>
        </th>`
    )
    .join("")}</tr>`;
  html += `<tr class="plan-week-row"><th class="plan-corner"></th>${weeks
    .map(
      (w) =>
        `<th>
          <span class="plan-week-label" onclick="editPlanWeek(${w.col}, '${(w.month || "").replace(/'/g, "\\'")}', '${(w.week || "").replace(/'/g, "\\'")}')">${w.week || ""}</span>
          <button class="plan-week-del" title="Eliminar esta semana" onclick="deletePlanWeek(${w.col}, '${(w.week || "").replace(/'/g, "\\'")}')">&times;</button>
        </th>`
    )
    .join("")}</tr>`;
  html += "</thead><tbody>";

  sections.forEach((section) => {
    const collapsed = state.planCollapsed.has(section.row);
    const arrow = collapsed ? "▸" : "▾";
    html += `<tr class="plan-section-row">
      <td colspan="${weeks.length + 1}">
        <span class="plan-section-toggle" onclick="togglePlanSection(${section.row})">${arrow} ${section.name} <span class="plan-section-count">${section.tasks.length}</span></span>
        <span class="plan-section-actions">
          <button class="plan-section-rename" title="Renombrar proyecto" onclick="renamePlanSection(${section.row}, '${section.name.replace(/'/g, "\\'")}')">✎</button>
          <button class="plan-section-del" title="Eliminar proyecto" onclick="deletePlanSection(${section.row}, '${section.name.replace(/'/g, "\\'")}')">&times;</button>
        </span>
      </td>
    </tr>`;
    if (collapsed) {
      html += `<tr class="plan-summary-row">
        <td class="plan-task-name plan-summary-name"></td>
        ${weeks
          .map((w) => {
            const cell = section.cells[w.col];
            const dataAttrs = section.row ? `data-row="${section.row}" data-col="${w.col}"` : "";
            if (cell) {
              return `<td class="plan-cell plan-summary-cell" style="background:${cell.color}" ${dataAttrs}>
                        <span class="plan-cell-label">${cell.label || ""}</span>
                      </td>`;
            }
            return `<td class="plan-cell plan-cell-empty" ${dataAttrs}></td>`;
          })
          .join("")}
      </tr>`;
      return;
    }
      section.tasks.forEach((task, taskIdx) => {
        const isFirst = taskIdx === 0;
        const isLast = taskIdx === section.tasks.length - 1;
        html += `<tr>
          <td class="plan-task-name">
            <span class="plan-task-move">
              <button class="plan-task-move-btn" title="Mover arriba" ${isFirst ? "disabled" : ""} onclick="movePlanTask(${task.row}, 'up')">▲</button>
              <button class="plan-task-move-btn" title="Mover abajo" ${isLast ? "disabled" : ""} onclick="movePlanTask(${task.row}, 'down')">▼</button>
            </span>
            <button class="plan-task-del" title="Eliminar tarea" onclick="deletePlanTask(${task.row}, '${task.name.replace(/'/g, "\\'")}')">&times;</button>
            <span class="plan-task-name-text" onclick="editPlanTaskName(${task.row}, '${task.name.replace(/'/g, "\\'")}', '${(task.notas || "").replace(/'/g, "\\'")}')">${task.name}</span>${noteBubbleIcon(task.notas, { title: "Ver comentario", onclick: `viewPlanTaskNota(${task.row})` })}
          </td>
          ${weeks
            .map((w) => {
              const cell = task.cells[w.col];
              if (cell) {
                return `<td class="plan-cell" style="background:${cell.color}"
                          data-row="${task.row}" data-col="${w.col}">
                          <span class="plan-cell-label">${cell.label || ""}</span>
                        </td>`;
              }
              return `<td class="plan-cell plan-cell-empty" data-row="${task.row}" data-col="${w.col}"></td>`;
            })
            .join("")}
        </tr>`;
      });
      html += `<tr class="plan-add-task-row" onclick="addPlanTask(${section.row})">
        <td colspan="${weeks.length + 1}">+ Agregar tarea en "${section.name}"</td>
      </tr>`;
  });

  html += `<tr class="plan-add-section-row" onclick="addPlanSection()">
    <td colspan="${weeks.length + 1}">+ Agregar nuevo proyecto</td>
  </tr>`;

  html += "</tbody>";
  table.innerHTML = html;
}

function togglePlanSection(row) {
  if (state.planCollapsed.has(row)) state.planCollapsed.delete(row);
  else state.planCollapsed.add(row);
  renderPlanificacion();
}

function getRowCellsMap(row) {
  const section = state.planificacion.sections.find(
    (s) => s.row === row || s.tasks.some((t) => t.row === row)
  );
  if (!section) return null;
  return section.row === row ? section.cells : section.tasks.find((t) => t.row === row).cells;
}

async function editPlanCellRange(row, cols) {
  const cellsMap = getRowCellsMap(row);
  if (!cellsMap) return;
  const sortedCols = [...cols].sort((a, b) => a - b);
  const single = sortedCols.length === 1;
  const existing = single ? cellsMap[sortedCols[0]] : null;

  const result = await openCellModal({
    title: single ? (existing ? "Editar semana" : "Marcar semana") : `Marcar ${sortedCols.length} semanas`,
    label: single && existing ? existing.label || "" : "",
    color: single && existing ? existing.color : "",
  });
  if (!result) return; // cancelled

  const active = result.action === "save";
  const label = active ? result.label : "";
  const color = active ? result.color : existing ? existing.color : "#F2A93B";

  try {
    if (single) {
      await api("/api/planificacion/cell", {
        method: "PUT",
        body: JSON.stringify({ row, col: sortedCols[0], active, label, color }),
      });
    } else {
      await api("/api/planificacion/cells", {
        method: "PUT",
        body: JSON.stringify({ cells: sortedCols.map((col) => ({ row, col })), active, label, color }),
      });
    }
    sortedCols.forEach((col) => {
      if (active) cellsMap[col] = { active: true, label, color };
      else delete cellsMap[col];
    });
    renderPlanificacion();
    if (!single) showToast(`${sortedCols.length} semanas actualizadas`);
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Drag / range selection over week cells ---------- */

const planSelect = { active: false, row: null, anchorCol: null, cols: [], lastRow: null, lastAnchorCol: null };

function planCellsInTable() {
  return document.querySelectorAll("#plan-table td.plan-cell[data-row]");
}

function applySelectionHighlight() {
  planCellsInTable().forEach((td) => {
    const row = Number(td.dataset.row);
    const col = Number(td.dataset.col);
    const inSelection = row === planSelect.row && planSelect.cols.includes(col);
    td.classList.toggle("plan-cell-selected", inSelection);
  });
}

function clearSelectionHighlight() {
  planCellsInTable().forEach((td) => td.classList.remove("plan-cell-selected"));
}

function startPlanSelection(row, col) {
  planSelect.active = true;
  planSelect.row = row;
  planSelect.anchorCol = col;
  planSelect.cols = [col];
  planSelect.lastRow = row;
  planSelect.lastAnchorCol = col;
  applySelectionHighlight();
}

function extendPlanSelection(row, col) {
  if (!planSelect.active || row !== planSelect.row) return;
  const lo = Math.min(planSelect.anchorCol, col);
  const hi = Math.max(planSelect.anchorCol, col);
  const cols = [];
  for (let c = lo; c <= hi; c++) cols.push(c);
  planSelect.cols = cols;
  applySelectionHighlight();
}

function shiftExtendPlanSelection(row, col) {
  // Extend from the last plain click/selection in the same row (Excel-style Shift+click).
  planSelect.active = true;
  planSelect.row = row;
  planSelect.anchorCol = planSelect.lastAnchorCol;
  extendPlanSelection(row, col);
}

function finishPlanSelection() {
  if (!planSelect.active) return;
  planSelect.active = false;
  const { row, cols } = planSelect;
  clearSelectionHighlight();
  if (row === null || !cols.length) return;
  editPlanCellRange(row, cols);
}

function wirePlanSelection() {
  const container = el("plan-table");

  container.addEventListener("mousedown", (e) => {
    const td = e.target.closest("td.plan-cell[data-row]");
    if (!td) return;
    e.preventDefault();
    const row = Number(td.dataset.row);
    const col = Number(td.dataset.col);

    if (e.shiftKey && planSelect.lastRow === row && planSelect.lastAnchorCol !== null) {
      shiftExtendPlanSelection(row, col);
    } else {
      startPlanSelection(row, col);
    }
  });

  container.addEventListener("mouseover", (e) => {
    if (!planSelect.active) return;
    const td = e.target.closest("td.plan-cell[data-row]");
    if (!td) return;
    extendPlanSelection(Number(td.dataset.row), Number(td.dataset.col));
  });

  document.addEventListener("mouseup", () => {
    if (planSelect.active) finishPlanSelection();
  });
}


async function addPlanTask(sectionRow) {
  const values = await openPlanFormModal({
    title: "Nueva tarea",
    submitLabel: "Agregar tarea",
    fields: [
      { name: "name", label: "Nombre de la tarea", placeholder: "ej: Desarrollo Front" },
      { name: "notas", label: "Notas (opcional)", type: "textarea" },
    ],
  });
  if (!values || !values.name) return;
  try {
    await api("/api/planificacion/task", {
      method: "POST",
      body: JSON.stringify({ section_row: sectionRow, name: values.name, notas: values.notas }),
    });
    showToast("Tarea agregada");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function addPlanSection() {
  const values = await openPlanFormModal({
    title: "Nuevo proyecto",
    submitLabel: "Agregar proyecto",
    fields: [{ name: "name", label: "Nombre del proyecto", placeholder: "ej: Checkout Rediseño" }],
  });
  if (!values || !values.name) return;
  try {
    await api("/api/planificacion/section", { method: "POST", body: JSON.stringify({ name: values.name }) });
    showToast("Proyecto agregado");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function addPlanMonth() {
  const values = await openPlanFormModal({
    title: "Agregar mes",
    submitLabel: "Agregar mes",
    fields: [
      { name: "month_name", label: "Nombre del mes", placeholder: "ej: Noviembre" },
      { name: "num_weeks", label: "Cantidad de semanas", type: "number", value: 4, min: 1, max: 6 },
    ],
  });
  if (!values || !values.month_name) return;
  const numWeeks = parseInt(values.num_weeks, 10) || 4;
  try {
    await api("/api/planificacion/month", {
      method: "POST",
      body: JSON.stringify({ month_name: values.month_name, num_weeks: numWeeks }),
    });
    showToast("Mes agregado");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

function findPlanTaskByRow(row) {
  if (!state.planificacion) return null;
  for (const section of state.planificacion.sections) {
    const found = section.tasks.find((t) => t.row === row);
    if (found) return found;
  }
  return null;
}

function viewPlanTaskNota(row) {
  const task = findPlanTaskByRow(row);
  if (!task) return;
  openTextViewerModal(task.name, task.notas || "");
}

async function editPlanTaskName(row, currentName, currentNotas) {
  const values = await openPlanFormModal({
    title: "Editar tarea",
    submitLabel: "Guardar",
    onDelete: () => deletePlanTask(row, currentName),
    deleteLabel: "Eliminar tarea",
    fields: [
      { name: "name", label: "Nombre de la tarea", value: currentName },
      { name: "notas", label: "Notas (opcional)", type: "textarea", value: currentNotas || "" },
    ],
  });
  if (!values || !values.name) return;
  try {
    await api(`/api/planificacion/task/${row}`, {
      method: "PUT",
      body: JSON.stringify({ name: values.name, notas: values.notas }),
    });
    showToast("Tarea actualizada");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function renamePlanSection(row, currentName) {
  const values = await openPlanFormModal({
    title: "Editar proyecto",
    submitLabel: "Guardar",
    onDelete: () => deletePlanSection(row, currentName),
    deleteLabel: "Eliminar proyecto",
    fields: [{ name: "name", label: "Nombre del proyecto", value: currentName }],
  });
  if (!values || !values.name) return;
  try {
    await api(`/api/planificacion/section/${row}`, {
      method: "PUT",
      body: JSON.stringify({ name: values.name }),
    });
    showToast("Proyecto actualizado");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editPlanWeek(col, currentMonth, currentWeek) {
  const values = await openPlanFormModal({
    title: "Editar semana",
    submitLabel: "Guardar",
    onDelete: () => deletePlanWeek(col, currentWeek),
    deleteLabel: "Eliminar semana",
    fields: [
      { name: "week", label: "Etiqueta de la semana", value: currentWeek || "", placeholder: "ej: sem 1" },
      { name: "month", label: "Mes", value: currentMonth || "", hint: "Deja igual si no cambia de mes" },
    ],
  });
  if (!values) return;
  try {
    await api(`/api/planificacion/week/${col}`, {
      method: "PUT",
      body: JSON.stringify({ week: values.week, month: values.month }),
    });
    showToast("Semana actualizada");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deletePlanWeek(col, weekLabel) {
  const ok = await openConfirmModal({
    title: "Eliminar semana",
    message: `¿Eliminar la columna "${weekLabel}"? Se perderán las marcas guardadas en esa semana para todas las tareas.`,
  });
  if (!ok) return;
  try {
    await api(`/api/planificacion/week/${col}`, { method: "DELETE" });
    showToast("Semana eliminada");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function movePlanTask(row, direction) {
  try {
    await api(`/api/planificacion/task/${row}/move`, {
      method: "POST",
      body: JSON.stringify({ direction }),
    });
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deletePlanTask(row, name) {
  const ok = await openConfirmModal({
    title: "Eliminar tarea",
    message: `¿Eliminar la tarea "${name}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/planificacion/task/${row}`, { method: "DELETE" });
    showToast("Tarea eliminada");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deletePlanSection(row, name) {
  const ok = await openConfirmModal({
    title: "Eliminar proyecto",
    message: `¿Eliminar el proyecto "${name}" y TODAS sus tareas? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/planificacion/section/${row}`, { method: "DELETE" });
    showToast("Proyecto eliminado");
    state.planCollapsed.delete(row);
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deletePlanMonth(monthName) {
  if (!monthName) return;
  const ok = await openConfirmModal({
    title: "Eliminar mes",
    message: `¿Eliminar todas las semanas de "${monthName}"? Se perderán las marcas guardadas en esas columnas.`,
  });
  if (!ok) return;
  try {
    await api("/api/planificacion/month", { method: "DELETE", body: JSON.stringify({ month_name: monthName }) });
    showToast("Mes eliminado");
    await loadPlanificacion();
    renderPlanificacion();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Equipo y Proyectos (Listas management) ---------- */

const LISTA_META = {
  Responsable: {
    domId: "Responsable", singular: "responsable",
    labelNew: "Nuevo responsable", labelEdit: "Editar responsable",
    fieldLabel: "Nombre del responsable", placeholder: "ej: Nombre (Rol)",
  },
  "Tipo de incidencia": {
    domId: "tipo-incidencia", singular: "tipo de incidencia",
    labelNew: "Nuevo tipo de incidencia", labelEdit: "Editar tipo de incidencia",
    fieldLabel: "Nombre del tipo de incidencia", placeholder: "ej: Precio, Stock, Sistema",
  },
  "Producto": {
    domId: "producto", singular: "producto",
    labelNew: "Nuevo producto", labelEdit: "Editar producto",
    fieldLabel: "Nombre del producto", placeholder: "ej: Back, Front, App",
  },
  "Tipo de Documento": {
    domId: "tipo-documento", singular: "tipo de documento",
    labelNew: "Nuevo tipo de documento", labelEdit: "Editar tipo de documento",
    fieldLabel: "Nombre del tipo de documento", placeholder: "ej: Minuta, Contrato, Manual",
  },
};

function countListaUsage(column, value) {
  if (column === "Responsable") {
    return (
      state.tareas.filter((t) => t.Responsable === value).length +
      state.incidencias.filter((i) => i["Responsable (seguimiento)"] === value).length +
      state.incidencias.filter((i) => i["Responsable (desarrollo)"] === value).length
    );
  }
  if (column === "Producto") return state.incidencias.filter((i) => i.Producto === value).length;
  if (column === "Tipo de incidencia") return state.incidencias.filter((i) => i["Tipo de incidencia"] === value).length;
  if (column === "Tipo de Documento") return state.documentos.filter((d) => d["Tipo de Documento"] === value).length;
  return 0;
}

function renderEquipo() {
  Object.keys(LISTA_META).forEach((column) => {
    const meta = LISTA_META[column];
    const items = (state.listas[column] || []).slice().sort((a, b) => a.localeCompare(b, "es"));
    const list = el(`equipo-list-${meta.domId}`);
    if (!items.length) {
      list.innerHTML = `<li class="equipo-list-empty">Sin ${meta.singular}s todavía.</li>`;
      return;
    }
    list.innerHTML = items
      .map((value) => {
        const count = countListaUsage(column, value);
        const safe = value.replace(/'/g, "\\'");
        return `<li class="equipo-item">
          <span class="equipo-item-name">${value} <span class="equipo-item-count">${count}</span></span>
          <span class="equipo-item-actions">
            <button class="equipo-item-edit" title="Renombrar" onclick="editListaItem('${column}', '${safe}')">✎</button>
            <button class="equipo-item-del" title="Eliminar" onclick="deleteListaItem('${column}', '${safe}')">&times;</button>
          </span>
        </li>`;
      })
      .join("");
  });
}

async function addListaItem(column) {
  const meta = LISTA_META[column];
  const values = await openPlanFormModal({
    title: meta.labelNew,
    submitLabel: "Agregar",
    fields: [{ name: "value", label: meta.fieldLabel, placeholder: meta.placeholder }],
  });
  if (!values || !values.value) return;
  try {
    await api(`/api/listas/${column}`, { method: "POST", body: JSON.stringify({ value: values.value }) });
    showToast(`Se agregó "${values.value}" a ${meta.singular}s`);
    await loadAll();
    renderEquipo();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editListaItem(column, oldValue) {
  const meta = LISTA_META[column];
  const values = await openPlanFormModal({
    title: meta.labelEdit,
    submitLabel: "Guardar",
    onDelete: () => deleteListaItem(column, oldValue),
    deleteLabel: "Eliminar",
    fields: [
      { name: "new_value", label: "Nombre", value: oldValue },
      {
        name: "cascade",
        label: "Actualizar también en los registros que ya usan este nombre",
        type: "checkbox",
        value: true,
        hint: "Si lo dejas marcado, los registros existentes se actualizan automáticamente al nuevo nombre.",
      },
    ],
  });
  if (!values || !values.new_value) return;
  if (values.new_value === oldValue) return;
  try {
    const res = await api(`/api/listas/${column}`, {
      method: "PUT",
      body: JSON.stringify({ old_value: oldValue, new_value: values.new_value, cascade: values.cascade }),
    });
    let msg = "Actualizado";
    if (values.cascade && (res.updated_tasks || res.updated_incidencias || res.updated_documentos)) {
      const parts = [];
      if (res.updated_tasks) parts.push(`${res.updated_tasks} tarea${res.updated_tasks === 1 ? "" : "s"}`);
      if (res.updated_incidencias) parts.push(`${res.updated_incidencias} incidencia${res.updated_incidencias === 1 ? "" : "s"}`);
      if (res.updated_documentos) parts.push(`${res.updated_documentos} documento${res.updated_documentos === 1 ? "" : "s"}`);
      msg = `Actualizado en ${parts.join(" y ")}`;
    }
    showToast(msg);
    await loadAll();
    renderEquipo();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteListaItem(column, value) {
  const count = countListaUsage(column, value);
  const singular = LISTA_META[column].singular;
  const message =
    count > 0
      ? `"${value}" está siendo usado por ${count} tarea${count === 1 ? "" : "s"}. Si lo eliminas de la lista, esas tareas mantendrán el texto pero ya no aparecerá como opción al crear nuevas tareas. ¿Eliminar igual?`
      : `¿Eliminar "${value}" de la lista de ${singular}s?`;
  const ok = await openConfirmModal({ title: "Eliminar de la lista", message });
  if (!ok) return;
  try {
    await api(`/api/listas/${column}`, { method: "DELETE", body: JSON.stringify({ value }) });
    showToast("Eliminado de la lista");
    await loadAll();
    renderEquipo();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Pasos a Prod ---------- */

function renderLinkOrText(value) {
  if (!value) return "";
  const isUrl = /^https?:\/\//i.test(value);
  if (!isUrl) return value;
  return `<a href="${value}" target="_blank" rel="noopener" class="pasos-link" onclick="event.stopPropagation()">${value}</a>`;
}

function renderPasosProd() {
  const rows = state.pasosProd;
  el("pasos-empty-state").style.display = rows.length ? "none" : "block";
  el("pasos-table-body").innerHTML = rows
    .map(
      (p) => `
    <tr data-row-id="${p.row_id}">
      <td>${p.Fecha || ""}</td>
      <td class="cell-tarea">${p.Tema || ""}</td>
      <td>${p.Producto || ""}</td>
      <td>${renderLinkOrText(p.OTC)}</td>
      <td>${renderLinkOrText(p["Ticket Jira"])}</td>
      <td><button class="icon-btn" onclick="event.stopPropagation(); editPasoProd(${p.row_id})">✎</button></td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#pasos-table-body tr").forEach((tr) => {
    tr.addEventListener("click", () => editPasoProd(Number(tr.dataset.rowId)));
  });
}

function toIsoDateFlexible(value) {
  if (!value) return "";
  const s = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s; // ya está en formato ISO
  const m = s.match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})$/); // ej: 13.07.2026
  if (m) {
    const [, d, mo, y] = m;
    return `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }
  return ""; // formato no reconocible: se deja vacío para forzar elegir una fecha válida
}

async function addPasoProd() {
  const values = await openPlanFormModal({
    title: "Nuevo paso a producción",
    submitLabel: "Agregar",
    fields: [
      { name: "Fecha", label: "Fecha", type: "date" },
      { name: "Tema", label: "Tema", placeholder: "ej: Cambio Nodeselector" },
      { name: "Producto", label: "Producto", placeholder: "ej: BO" },
      { name: "OTC", label: "OTC", placeholder: "ej: OTC-5897 o link completo" },
      { name: "Ticket Jira", label: "Ticket Jira", placeholder: "link completo del ticket" },
    ],
  });
  if (!values) return;
  try {
    await api("/api/pasos-prod", { method: "POST", body: JSON.stringify(values) });
    showToast("Paso a producción agregado");
    await loadAll();
    renderPasosProd();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editPasoProd(rowId) {
  const p = state.pasosProd.find((x) => x.row_id === rowId);
  if (!p) return;
  const values = await openPlanFormModal({
    title: "Editar paso a producción",
    submitLabel: "Guardar",
    onDelete: () => deletePasoProd(rowId, p.Tema),
    deleteLabel: "Eliminar",
    fields: [
      { name: "Fecha", label: "Fecha", type: "date", value: toIsoDateFlexible(p.Fecha) },
      { name: "Tema", label: "Tema", value: p.Tema || "" },
      { name: "Producto", label: "Producto", value: p.Producto || "" },
      { name: "OTC", label: "OTC", value: p.OTC || "" },
      { name: "Ticket Jira", label: "Ticket Jira", value: p["Ticket Jira"] || "" },
    ],
  });
  if (!values) return;
  try {
    await api(`/api/pasos-prod/${rowId}`, { method: "PUT", body: JSON.stringify(values) });
    showToast("Paso a producción actualizado");
    await loadAll();
    renderPasosProd();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deletePasoProd(rowId, tema) {
  const ok = await openConfirmModal({
    title: "Eliminar paso a producción",
    message: `¿Eliminar "${tema || "este paso a producción"}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/pasos-prod/${rowId}`, { method: "DELETE" });
    showToast("Eliminado");
    await loadAll();
    renderPasosProd();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Incidencias ---------- */

function incidenciaBadge(estado) {
  if (!estado) return "";
  return `<span class="badge badge-incidencia-${slug(estado)}">${estado}</span>`;
}

function getFilteredIncidencias() {
  const { estado, responsableSeguimiento, responsableDesarrollo } = state.incidenciaFilters;
  const rows = state.incidencias.filter((i) => {
    if (estado && i.Estado !== estado) return false;
    if (responsableSeguimiento && i["Responsable (seguimiento)"] !== responsableSeguimiento) return false;
    if (responsableDesarrollo && i["Responsable (desarrollo)"] !== responsableDesarrollo) return false;
    return true;
  });

  const { column, dir } = state.incidenciaSort;
  if (column) {
    const mult = dir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      const va = a[column];
      const vb = b[column];
      const aEmpty = va === null || va === undefined || va === "";
      const bEmpty = vb === null || vb === undefined || vb === "";
      if (aEmpty && bEmpty) return 0;
      if (aEmpty) return 1; // las incidencias sin prioridad quedan al final, sin importar el sentido
      if (bEmpty) return -1;
      if (va < vb) return -1 * mult;
      if (va > vb) return 1 * mult;
      return 0;
    });
  }
  return rows;
}

function setIncidenciaSort(column) {
  if (state.incidenciaSort.column === column) {
    state.incidenciaSort.dir = state.incidenciaSort.dir === "asc" ? "desc" : "asc";
  } else {
    state.incidenciaSort = { column, dir: "asc" };
  }
  renderIncidencias();
}

function renderIncidencias() {
  const rows = getFilteredIncidencias();
  const th = el("th-incidencia-prioridad");
  th.classList.remove("sort-asc", "sort-desc");
  if (state.incidenciaSort.column === "Prioridad") {
    th.classList.add(state.incidenciaSort.dir === "desc" ? "sort-desc" : "sort-asc");
  }
  el("incidencias-empty-state").style.display = rows.length ? "none" : "block";
  el("incidencias-empty-state").textContent =
    state.incidencias.length && !rows.length
      ? "No hay incidencias que calcen con los filtros elegidos."
      : "No hay incidencias registradas todavía.";
  el("incidencias-table-body").innerHTML = rows
    .map(
      (i) => `
    <tr data-row-id="${i.row_id}">
      <td>${i["Fecha de reporte"] || ""}</td>
      <td>${i.Cantidad ?? ""}</td>
      <td>${i.Producto || ""}</td>
      <td>${i["Título"] || ""}</td>
      <td>${i["Tipo de incidencia"] || ""}</td>
      <td class="cell-descripcion cell-descripcion-click" onclick="event.stopPropagation(); editIncidenciaDescripcion(${i.row_id})"><span class="notas-clamp-5">${i["Descripción"] || ""}</span></td>
      <td>${badge("prioridad", i.Severidad)}</td>
      <td class="cell-prioridad-num">${i.Prioridad ?? ""}</td>
      <td>${incidenciaBadge(i.Estado)}</td>
      <td>${i["Responsable (seguimiento)"] || ""}</td>
      <td>${i["Responsable (desarrollo)"] || ""}</td>
      <td>${renderLinkOrText(i["Ticket Jira"])}</td>
      <td>${i["Fecha de resolución"] || ""}</td>
      <td class="cell-notas"><span class="notas-clamp">${i["Solución aplicada"] || ""}</span></td>
      <td><button class="icon-btn" onclick="event.stopPropagation(); editIncidencia(${i.row_id})">✎</button>${noteBubbleIcon(i.Log, { title: "Ver log", icon: "🧾", onclick: `viewIncidenciaLog(${i.row_id})` })}</td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#incidencias-table-body tr").forEach((tr) => {
    tr.addEventListener("click", () => editIncidencia(Number(tr.dataset.rowId)));
  });
}

function incidenciaFields(values = {}) {
  const tipos = state.listas["Tipo de incidencia"] || [];
  const productos = state.listas.Producto || [];
  const responsables = state.listas.Responsable || [];
  const colorMap = {};
  Object.entries(state.incidenciaEstadoColors).forEach(([k, v]) => (colorMap[k] = v));

  return [
    { name: "Fecha de reporte", label: "Fecha de reporte", type: "date", value: values["Fecha de reporte"] || "" },
    {
      name: "Cantidad", label: "Cantidad", type: "number", min: 1, value: values.Cantidad ?? 1,
      hint: "Veces que se repitió esta incidencia puntual (ej: 4 = se reportó 4 veces).",
    },
    { name: "Producto", label: "Producto", type: "combo", value: values.Producto || "", options: productos, placeholder: "ej: Back, Front, App" },
    { name: "Título", label: "Título", value: values["Título"] || "", placeholder: "ej: Precio incorrecto en góndola" },
    { name: "Tipo de incidencia", label: "Tipo de incidencia", type: "combo", value: values["Tipo de incidencia"] || "", options: tipos, placeholder: "ej: Precio" },
    { name: "Descripción", label: "Descripción", type: "textarea", value: values["Descripción"] || "" },
    { name: "Severidad", label: "Severidad/Prioridad", type: "select", value: values.Severidad || "Media", options: ["Baja", "Media", "Alta"] },
    {
      name: "Prioridad", label: "Prioridad (1 a 10)", type: "number", min: 1, max: 10, value: values.Prioridad ?? "",
      hint: "1 = más urgente, 10 = menos urgente.",
    },
    { name: "Estado", label: "Estado", type: "select", value: values.Estado || state.incidenciaEstados[0], options: state.incidenciaEstados, colorMap },
    { name: "Responsable (seguimiento)", label: "Responsable (seguimiento)", type: "combo", strict: true, value: values["Responsable (seguimiento)"] || "", options: responsables, placeholder: "ej: Nombre (Rol)" },
    { name: "Responsable (desarrollo)", label: "Responsable (desarrollo)", type: "combo", strict: true, value: values["Responsable (desarrollo)"] || "", options: responsables, placeholder: "ej: Nombre (Rol)" },
    { name: "Ticket Jira", label: "Ticket Jira", value: values["Ticket Jira"] || "", placeholder: "link completo del ticket" },
    { name: "Fecha de resolución", label: "Fecha de resolución", type: "date", value: values["Fecha de resolución"] || "" },
    { name: "Solución aplicada", label: "Solución aplicada", type: "textarea", value: values["Solución aplicada"] || "" },
    { name: "Log", label: "Log / evidencia técnica (opcional)", type: "textarea", rows: 6, mono: true, value: values.Log || "", placeholder: "Pega aquí un log, stack trace o salida de consola…" },
  ];
}

async function addIncidencia() {
  const values = await openPlanFormModal({
    title: "Nueva incidencia",
    submitLabel: "Agregar",
    fields: incidenciaFields(),
  });
  if (!values) return;
  try {
    await api("/api/incidencias", { method: "POST", body: JSON.stringify(values) });
    showToast("Incidencia registrada");
    await loadAll();
    renderIncidencias();
  } catch (e) {
    showToast(e.message, true);
  }
}

function viewIncidenciaLog(rowId) {
  const i = state.incidencias.find((x) => x.row_id === rowId);
  if (!i) return;
  openTextViewerModal(`Log — ${i["Título"] || "Incidencia"}`, i.Log || "", { mono: true });
}

async function editIncidenciaDescripcion(rowId) {
  const i = state.incidencias.find((x) => x.row_id === rowId);
  if (!i) return;
  const values = await openPlanFormModal({
    title: i["Título"] ? `Descripción — ${i["Título"]}` : "Descripción",
    submitLabel: "Guardar",
    fields: [{ name: "Descripción", label: "Descripción", type: "textarea", rows: 14, value: i["Descripción"] || "" }],
  });
  if (!values) return;
  try {
    await api(`/api/incidencias/${rowId}`, { method: "PUT", body: JSON.stringify({ Descripción: values["Descripción"] }) });
    showToast("Descripción actualizada");
    await loadAll();
    renderIncidencias();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editIncidencia(rowId) {
  const i = state.incidencias.find((x) => x.row_id === rowId);
  if (!i) return;
  const values = await openPlanFormModal({
    title: "Editar incidencia",
    submitLabel: "Guardar",
    onDelete: () => deleteIncidencia(rowId, i["Descripción"]),
    deleteLabel: "Eliminar",
    fields: incidenciaFields(i),
  });
  if (!values) return;
  try {
    await api(`/api/incidencias/${rowId}`, { method: "PUT", body: JSON.stringify(values) });
    showToast("Incidencia actualizada");
    await loadAll();
    renderIncidencias();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteIncidencia(rowId, descripcion) {
  const ok = await openConfirmModal({
    title: "Eliminar incidencia",
    message: `¿Eliminar "${descripcion || "esta incidencia"}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/incidencias/${rowId}`, { method: "DELETE" });
    showToast("Incidencia eliminada");
    await loadAll();
    renderIncidencias();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function importIncidenciasCsv(file) {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await fetch("/api/incidencias/import-csv", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "Error al importar el CSV");

    if (data.missing_columns && data.missing_columns.length) {
      showToast(`Importado, pero faltan columnas: ${data.missing_columns.join(", ")}`, true);
    } else if (data.errors && data.errors.length) {
      showToast(`Se importaron ${data.imported} filas, con ${data.errors.length} error(es). Revisa la consola.`, true);
      console.warn("Errores al importar CSV de incidencias:", data.errors);
    } else {
      showToast(`Se importaron ${data.imported} incidencia${data.imported === 1 ? "" : "s"} desde el CSV`);
    }
    await loadAll();
    renderIncidencias();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Documentación: sub-navegación ---------- */

function renderDocumentacion() {
  if (state.docSub === "links") renderLinks();
  else if (state.docSub === "documentos") renderDocumentos();
  else if (state.docSub === "diagramas") renderDiagramas();
  // "excalidraw" es solo el iframe estático, no requiere render
}

/* ---------- Links ---------- */

function renderLinks() {
  const rows = state.links;
  el("links-empty-state").style.display = rows.length ? "none" : "block";
  el("links-table-body").innerHTML = rows
    .map(
      (l) => `
    <tr data-row-id="${l.row_id}">
      <td>${l.Fecha || ""}</td>
      <td>${renderLinkOrText(l.URL)}</td>
      <td class="cell-notas"><span class="notas-clamp">${l.Comentario || ""}</span></td>
      <td>${l.Autor || ""}</td>
      <td><button class="icon-btn" onclick="event.stopPropagation(); editLink(${l.row_id})">✎</button></td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#links-table-body tr").forEach((tr) => {
    tr.addEventListener("click", () => editLink(Number(tr.dataset.rowId)));
  });
}

async function addLink() {
  const responsables = state.listas.Responsable || [];
  const values = await openPlanFormModal({
    title: "Nuevo link",
    submitLabel: "Agregar",
    fields: [
      { name: "URL", label: "URL", placeholder: "https://…" },
      { name: "Comentario", label: "Comentario (opcional)", placeholder: "¿Qué es este link?" },
      { name: "Autor", label: "Autor (opcional)", type: "combo", options: responsables, placeholder: "ej: Nombre (Rol)" },
    ],
  });
  if (!values || !values.URL) return;
  try {
    await api("/api/links", { method: "POST", body: JSON.stringify(values) });
    showToast("Link agregado");
    await loadAll();
    renderLinks();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function editLink(rowId) {
  const l = state.links.find((x) => x.row_id === rowId);
  if (!l) return;
  const responsables = state.listas.Responsable || [];
  const values = await openPlanFormModal({
    title: "Editar link",
    submitLabel: "Guardar",
    onDelete: () => deleteLink(rowId, l.URL),
    fields: [
      { name: "URL", label: "URL", value: l.URL || "" },
      { name: "Comentario", label: "Comentario (opcional)", value: l.Comentario || "" },
      { name: "Autor", label: "Autor (opcional)", type: "combo", value: l.Autor || "", options: responsables },
    ],
  });
  if (!values || !values.URL) return;
  try {
    await api(`/api/links/${rowId}`, { method: "PUT", body: JSON.stringify(values) });
    showToast("Link actualizado");
    await loadAll();
    renderLinks();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteLink(rowId, url) {
  const ok = await openConfirmModal({
    title: "Eliminar link",
    message: `¿Eliminar "${url || "este link"}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/links/${rowId}`, { method: "DELETE" });
    showToast("Link eliminado");
    await loadAll();
    renderLinks();
  } catch (e) {
    showToast(e.message, true);
  }
}

/* ---------- Documentos y Diagramas (archivos) ---------- */

function formatBytes(bytes) {
  if (!bytes) return "";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function renderDocumentos() {
  const rows = state.documentos;
  el("documentos-empty-state").style.display = rows.length ? "none" : "block";
  el("documentos-table-body").innerHTML = rows
    .map(
      (d) => `
    <tr data-row-id="${d.row_id}">
      <td>${d.Fecha || ""}</td>
      <td class="cell-tarea">${d.Nombre || ""}</td>
      <td>${d["Proyecto vinculado"] || ""}</td>
      <td>${d["Tipo de Documento"] || ""}</td>
      <td class="cell-notas"><span class="notas-clamp">${d.Comentario || ""}</span></td>
      <td>${d.Autor || ""}</td>
      <td>${formatBytes(d["Tamaño"])}</td>
      <td>
        <a class="icon-btn" title="Descargar" href="/api/documentos/${d.row_id}/descargar">⬇</a>
        <button class="icon-btn" title="Eliminar" onclick="deleteDocumento(${d.row_id}, '${(d.Nombre || "").replace(/'/g, "\\'")}')">✕</button>
      </td>
    </tr>`
    )
    .join("");
}

async function deleteDocumento(rowId, nombre) {
  const ok = await openConfirmModal({
    title: "Eliminar documento",
    message: `¿Eliminar "${nombre || "este documento"}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/documentos/${rowId}`, { method: "DELETE" });
    showToast("Documento eliminado");
    await loadAll();
    renderDocumentos();
  } catch (e) {
    showToast(e.message, true);
  }
}

let pendingDocumentoMeta = null;

async function addDocumento() {
  const proyectos = proyectoNombres();
  const tipos = state.listas["Tipo de Documento"] || [];
  const responsables = state.listas.Responsable || [];
  const values = await openPlanFormModal({
    title: "Subir documento",
    submitLabel: "Elegir archivo…",
    fields: [
      { name: "Proyecto vinculado", label: "Proyecto vinculado (opcional)", type: "combo", options: proyectos, placeholder: "ej: Robustecimiento" },
      { name: "Tipo de Documento", label: "Tipo de documento (opcional)", type: "combo", options: tipos, placeholder: "ej: Minuta" },
      { name: "Comentario", label: "Comentario (opcional)", type: "textarea" },
      { name: "Autor", label: "Autor (opcional)", type: "combo", options: responsables, placeholder: "ej: Nombre (Rol)" },
    ],
  });
  if (!values) return;
  pendingDocumentoMeta = values;
  el("documento-file-input").click();
}

async function subirArchivoConMeta(inputId, endpoint, meta, onDone) {
  const fileInput = el(inputId);
  const file = fileInput.files[0];
  fileInput.value = "";
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  Object.entries(meta || {}).forEach(([k, v]) => formData.append(k, v || ""));
  try {
    const res = await fetch(endpoint, { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "Error al subir el archivo");
    showToast("Archivo guardado");
    await loadAll();
    onDone();
  } catch (e) {
    showToast(e.message, true);
  }
}

function renderDiagramas() {
  const rows = state.diagramas;
  el("diagramas-empty-state").style.display = rows.length ? "none" : "block";
  el("diagramas-table-body").innerHTML = rows
    .map(
      (d) => `
    <tr data-row-id="${d.row_id}">
      <td>${d.Fecha || ""}</td>
      <td class="cell-tarea">${d.Nombre || ""}</td>
      <td class="cell-notas"><span class="notas-clamp">${d.Comentario || ""}</span></td>
      <td>${d.Autor || ""}</td>
      <td>${formatBytes(d["Tamaño"])}</td>
      <td>
        <a class="icon-btn" title="Descargar" href="/api/diagramas/${d.row_id}/descargar">⬇</a>
        <button class="icon-btn" title="Eliminar" onclick="deleteDiagrama(${d.row_id}, '${(d.Nombre || "").replace(/'/g, "\\'")}')">✕</button>
      </td>
    </tr>`
    )
    .join("");
}

async function deleteDiagrama(rowId, nombre) {
  const ok = await openConfirmModal({
    title: "Eliminar diagrama",
    message: `¿Eliminar "${nombre || "este diagrama"}"? Esta acción no se puede deshacer.`,
  });
  if (!ok) return;
  try {
    await api(`/api/diagramas/${rowId}`, { method: "DELETE" });
    showToast("Diagrama eliminado");
    await loadAll();
    renderDiagramas();
  } catch (e) {
    showToast(e.message, true);
  }
}

let pendingDiagramaMeta = null;

async function addDiagrama() {
  const responsables = state.listas.Responsable || [];
  const values = await openPlanFormModal({
    title: "Subir diagrama",
    submitLabel: "Elegir archivo…",
    fields: [
      { name: "Comentario", label: "Comentario (opcional)", placeholder: "¿Qué documenta este diagrama?" },
      { name: "Autor", label: "Autor (opcional)", type: "combo", options: responsables, placeholder: "ej: Nombre (Rol)" },
    ],
  });
  if (!values) return;
  pendingDiagramaMeta = values;
  el("diagrama-file-input").click();
}

/* ---------- Respaldo en Supabase ---------- */

async function backupToSupabase() {
  const btn = el("btn-backup-supabase");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Respaldando…";
  try {
    const res = await fetch("/api/backup/supabase", { method: "POST" });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "Error al respaldar");
    showToast(`Respaldo guardado en Supabase (${data.uploaded.join(", ")})`);
  } catch (e) {
    showToast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function limpiarRespaldosAntiguos() {
  const ok = await openConfirmModal({
    title: "Limpiar respaldos antiguos",
    message: "Esto elimina en Supabase los respaldos de Excel con marca de tiempo que quedaron de versiones anteriores (ya no se generan). El respaldo actual no se toca. ¿Continuar?",
  });
  if (!ok) return;
  const btn = el("btn-limpiar-supabase");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Limpiando…";
  try {
    const res = await fetch("/api/backup/supabase/limpiar", { method: "POST" });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.error || "Error al limpiar");
    showToast(data.deleted > 0 ? `Se eliminaron ${data.deleted} respaldo(s) antiguo(s)` : "No había respaldos antiguos que limpiar");
  } catch (e) {
    showToast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

/* ---------- Visor de texto (notas/log): icono -> clic -> ver ---------- */

let _viewModalRawContent = "";

function openTextViewerModal(title, content, { mono = false } = {}) {
  el("view-modal-title").textContent = title || "Detalle";
  const box = el("view-modal-content");
  box.textContent = content || "(sin contenido)";
  box.classList.toggle("mono", !!mono);
  _viewModalRawContent = content || "";
  el("view-modal-overlay").classList.add("active");
}

function closeViewModal() {
  el("view-modal-overlay").classList.remove("active");
}

async function copyViewModalContent() {
  try {
    await navigator.clipboard.writeText(_viewModalRawContent);
    showToast("Copiado al portapapeles");
  } catch (e) {
    showToast("No se pudo copiar automáticamente, selecciona el texto manualmente", true);
  }
}

function noteBubbleIcon(text, { title = "Ver comentario", icon = "💬", onclick }) {
  if (!text) return "";
  return `<button class="note-bubble-btn" title="${title}" onclick="event.stopPropagation(); ${onclick}">${icon}</button>`;
}

/* ---------- Modal / CRUD ---------- */

function openNew() {
  state.editingRowId = null;
  el("modal-title").textContent = "Nueva tarea";
  el("tarea-form").reset();
  el("btn-delete").style.display = "none";
  el("modal-overlay").classList.add("active");
}

function viewTareaLog(rowId) {
  const t = state.tareas.find((x) => x.row_id === rowId);
  if (!t) return;
  openTextViewerModal(`Log — ${t.Tarea || "Tarea"}`, t.Log || "", { mono: true });
}

function openEdit(rowId) {
  const t = state.tareas.find((x) => x.row_id === rowId);
  if (!t) return;
  state.editingRowId = rowId;
  el("modal-title").textContent = "Editar tarea";
  const form = el("tarea-form");
  form.reset();
  Object.entries(t).forEach(([key, value]) => {
    const input = form.elements[key];
    if (!input) return;
    if (input.type === "checkbox") {
      input.checked = value === "Sí";
    } else {
      input.value = value ?? "";
    }
  });
  el("btn-delete").style.display = "inline-block";
  el("modal-overlay").classList.add("active");
}

function closeModal() {
  el("modal-overlay").classList.remove("active");
}

async function handleSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const payload = {};
  new FormData(form).forEach((value, key) => (payload[key] = value));
  // Los checkboxes no aparecen en FormData cuando están desmarcados; hay que
  // fijar el valor explícitamente para que un "desmarcar" también se guarde.
  payload["Clave"] = form.elements["Clave"].checked ? "Sí" : "";

  try {
    if (state.editingRowId) {
      await api(`/api/tareas/${state.editingRowId}`, { method: "PUT", body: JSON.stringify(payload) });
      showToast("Tarea actualizada");
    } else {
      await api("/api/tareas", { method: "POST", body: JSON.stringify(payload) });
      showToast("Tarea creada");
    }
    closeModal();
    await loadAll();
    state.planificacion = null; // por si la tarea quedó vinculada/desvinculada del Roadmap
  } catch (err) {
    showToast(err.message, true);
  }
}

async function handleDelete() {
  if (!state.editingRowId) return;
  if (!confirm("¿Eliminar esta tarea? Esta acción no se puede deshacer.")) return;
  try {
    await api(`/api/tareas/${state.editingRowId}`, { method: "DELETE" });
    showToast("Tarea eliminada");
    closeModal();
    await loadAll();
    state.planificacion = null; // por si la tarea eliminada estaba vinculada al Roadmap
  } catch (err) {
    showToast(err.message, true);
  }
}

/* ---------- Wiring ---------- */

function wireEvents() {
  el("btn-new").addEventListener("click", openNew);
  el("btn-cancel").addEventListener("click", closeModal);
  el("modal-close").addEventListener("click", closeModal);
  el("tarea-form").addEventListener("submit", handleSubmit);
  el("btn-delete").addEventListener("click", handleDelete);
  el("btn-export").addEventListener("click", () => (window.location.href = "/api/export"));
  el("btn-backup-supabase").addEventListener("click", backupToSupabase);
  el("btn-limpiar-supabase").addEventListener("click", limpiarRespaldosAntiguos);
  el("roadmap-year-prev").addEventListener("click", () => {
    state.roadmapYear -= 1;
    renderRoadmap();
  });
  el("roadmap-year-next").addEventListener("click", () => {
    state.roadmapYear += 1;
    renderRoadmap();
  });
  el("btn-pasos-new").addEventListener("click", addPasoProd);
  el("btn-incidencias-new").addEventListener("click", addIncidencia);
  el("btn-incidencias-import").addEventListener("click", () => el("incidencias-csv-input").click());
  el("incidencias-csv-input").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) importIncidenciasCsv(file);
    e.target.value = "";
  });
  el("f-incidencia-estado").addEventListener("change", (e) => {
    state.incidenciaFilters.estado = e.target.value;
    renderIncidencias();
  });
  el("f-incidencia-responsable-seguimiento").addEventListener("change", (e) => {
    state.incidenciaFilters.responsableSeguimiento = e.target.value;
    renderIncidencias();
  });
  el("f-incidencia-responsable-desarrollo").addEventListener("change", (e) => {
    state.incidenciaFilters.responsableDesarrollo = e.target.value;
    renderIncidencias();
  });
  el("th-incidencia-prioridad").addEventListener("click", () => setIncidenciaSort("Prioridad"));

  el("btn-link-new").addEventListener("click", addLink);
  el("btn-documento-upload").addEventListener("click", addDocumento);
  el("documento-file-input").addEventListener("change", () =>
    subirArchivoConMeta("documento-file-input", "/api/documentos", pendingDocumentoMeta, renderDocumentos)
  );
  el("btn-diagrama-upload").addEventListener("click", addDiagrama);
  el("diagrama-file-input").addEventListener("change", () =>
    subirArchivoConMeta("diagrama-file-input", "/api/diagramas", pendingDiagramaMeta, renderDiagramas)
  );
  document.querySelectorAll(".doc-subnav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".doc-subnav-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.docSub = btn.dataset.docsub;
      document.querySelectorAll(".doc-subpanel").forEach((p) => p.classList.remove("active"));
      el(`docsub-${state.docSub}`).classList.add("active");
      renderDocumentacion();
    });
  });

  attachCombobox(document.querySelector('[data-combo-list="Responsable"]'), () => state.listas.Responsable || []);

  document.querySelectorAll(".view-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".view-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.view = btn.dataset.view;
      document.querySelectorAll(".view-panel").forEach((p) => p.classList.remove("active"));
      el(`view-${state.view}`).classList.add("active");
      el("filters-bar").style.display = ["planificacion", "equipo", "pasosprod", "incidencias", "documentacion"].includes(state.view) ? "none" : "flex";
      render();
    });
  });

  ["f-proyecto", "f-estado", "f-prioridad", "f-responsable"].forEach((id) => {
    el(id).addEventListener("change", (e) => {
      const key = id.replace("f-", "");
      state.filters[key] = e.target.value;
      render();
    });
  });
  el("f-search").addEventListener("input", (e) => {
    state.filters.search = e.target.value;
    render();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal();
      closePlanFormModal(null);
      closeConfirmModal(false);
      closeCellModal(null);
      closeViewModal();
    }
  });
  el("view-modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "view-modal-overlay") closeViewModal();
  });
}

wireEvents();
// wirePlanSelection() ya no se invoca: pertenecía a la grilla semanal manual
// de Planificación (reemplazada por el Roadmap tipo Gantt derivado de
// Proyectos + Tareas clave). Se deja la función sin usar por si se necesita
// referencia histórica, pero no se ejecuta.
loadAll();
