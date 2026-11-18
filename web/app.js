/* ──────────────────────────────────────────────────────────────────────────
   Ac2ality Digest · lógica de la interfaz
   Funciona en dos modos:
     · desktop → dentro de la app de Windows/macOS. Puede descargar noticias
                 al momento (/api/refresh) y muestra el progreso en directo.
     · web     → iPhone / navegador (PWA). Lee el digest.json que GitHub
                 Actions publica varias veces al día.
   ────────────────────────────────────────────────────────────────────────── */
(() => {
  "use strict";

  const RUNTIME = document.querySelector('meta[name="ac2-runtime"]')?.content || "web";
  const TOKEN = document.querySelector('meta[name="ac2-token"]')?.content || "";
  const IS_DESKTOP = RUNTIME === "desktop";
  const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const IS_STANDALONE = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  const CATEGORY_COLORS = {
    "SUCESOS": "#3374D6",
    "SOCIEDAD": "#7734BA",
    "POLÍTICA / LEYES": "#AD2638",
    "MUNDO": "#266EAD",
    "DEPORTES": "#E39A00",
    "CULTURA POP": "#D63387",
    "TECNOLOGÍA E IA": "#0A68F5",
    "CIENCIA Y SALUD": "#098227",
    "CONSUMO / ECONOMÍA": "#8A9A0B",
    "EDUCACIÓN": "#F5830A",
    "MEDIO AMBIENTE / CLIMA": "#17A81C",
    "OTRAS": "#224E63",
  };
  const colorFor = (category) => CATEGORY_COLORS[category] || CATEGORY_COLORS.OTRAS;

  const KEYS = {
    saved: "ac2alityDigestCurated",      // mismo nombre que la versión anterior: no se pierde nada
    seen: "ac2alityDigestSeen",
    theme: "ac2alityTheme",
    view: "ac2alityView",
  };

  const AUTO_REFRESH_AFTER_MIN = 120;   // escritorio: si el digest tiene más de 2 h, se actualiza solo al abrir

  // ── Estado ────────────────────────────────────────────────────────────────
  const state = {
    digest: null,
    all: [],
    filtered: [],
    newIds: new Set(),
    selected: new Set(),
    filters: { category: "", source: "", sensitive: "", sort: "score", query: "" },
    job: null,
    jobStartedAt: 0,
    overlayMinimized: false,
    pollTimer: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    freshness: $("freshness"), freshnessText: $("freshness-text"),
    refreshBtn: $("refresh-btn"), refreshLabel: $("refresh-label"),
    savedBtn: $("saved-btn"), savedBadge: $("saved-badge"), themeBtn: $("theme-btn"),
    miniProgress: $("mini-progress"), miniFill: $("mini-progress-fill"), miniText: $("mini-progress-text"),
    tabs: $("category-tabs"), search: $("search-input"), sort: $("sort-filter"), source: $("source-filter"),
    stats: $("stats"), status: $("status-text"), selectAll: $("select-all-btn"), clearFilters: $("clear-filters-btn"),
    content: $("content"), footer: $("footer"),
    actionBar: $("action-bar"), selectedCount: $("selected-count"), selectedLabel: $("selected-label"),
    overlay: $("refresh-overlay"), ring: $("ring"), ringFill: $("ring-fill"), ringValue: $("ring-value"),
    refreshTitle: $("refresh-title"), refreshSub: $("refresh-sub"),
    rcSources: $("rc-sources"), rcArticles: $("rc-articles"), rcTime: $("rc-time"),
    steps: $("refresh-steps"), sourceGrid: $("source-grid"),
    minimizeBtn: $("minimize-btn"), refreshCloseBtn: $("refresh-close-btn"),
    drawerOverlay: $("drawer-overlay"), drawerTitle: $("drawer-title"), drawerBody: $("drawer-body"), drawerClose: $("drawer-close"),
    toast: $("toast"),
  };

  // ── Utilidades ────────────────────────────────────────────────────────────
  const storage = {
    get(key, fallback) {
      try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* modo privado */ }
    },
  };

  const esc = (value) => String(value ?? "").replace(/[&<>"'`]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" }[c]));
  const normalize = (text) => String(text || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  function relativeTime(date) {
    const minutes = Math.round((Date.now() - date.getTime()) / 60000);
    if (minutes < 1) return "ahora mismo";
    if (minutes < 60) return `hace ${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `hace ${hours} h${minutes % 60 && hours < 5 ? ` ${minutes % 60} min` : ""}`;
    const days = Math.floor(hours / 24);
    return `hace ${plural(days, "día", "días")}`;
  }

  function articleDate(article) {
    const value = Date.parse(article.published_iso || "");
    return Number.isNaN(value) ? 0 : value;
  }

  function shortDate(article) {
    const value = articleDate(article);
    if (!value) return article.published_local || "sin fecha";
    const date = new Date(value);
    const today = new Date();
    const time = date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    if (date.toDateString() === today.toDateString()) return `Hoy ${time}`;
    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return `Ayer ${time}`;
    return date.toLocaleDateString("es-ES", { day: "2-digit", month: "short" }) + ` ${time}`;
  }

  function showToast(message, ms = 2600) {
    els.toast.textContent = message;
    els.toast.classList.add("show");
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => els.toast.classList.remove("show"), ms);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      cache: "no-store",
      ...options,
      headers: { "Content-Type": "application/json", "X-Ac2-Token": TOKEN, ...(options.headers || {}) },
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  // ── Carga del digest ──────────────────────────────────────────────────────
  async function fetchDigest() {
    const response = await fetch(`digest.json?ts=${Date.now()}`, { cache: "no-store" });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`No se pudo leer el digest (${response.status})`);
    return response.json();
  }

  function normalizeArticles(data) {
    let list = Array.isArray(data?.articles) ? data.articles : [];
    if (!list.length && Array.isArray(data?.sources)) {
      list = data.sources.flatMap((s) => (s.articles || []).map((a) => ({ ...a, source: a.source || s.name })));
    }
    const seen = new Set();
    return list
      .filter((a) => a && a.title && a.url)
      .map((a, i) => ({
        id: a.id || `a${i}`,
        title: a.title,
        url: a.url,
        image: a.image || "",
        source: a.source || "Fuente",
        published_local: a.published_local || a.published || "",
        published_iso: a.published_iso || "",
        category: a.category || "OTRAS",
        score: Number(a.score || 0),
        matched_keywords: Array.isArray(a.matched_keywords) ? a.matched_keywords : [],
        is_sensitive: Boolean(a.is_sensitive),
        sensitive_terms: Array.isArray(a.sensitive_terms) ? a.sensitive_terms : [],
        editorial_risk: a.editorial_risk || "",
        needs_human_review: Boolean(a.needs_human_review),
        recommended_format: a.recommended_format || "",
        summary: a.summary || "",
      }))
      .filter((a) => (seen.has(a.id) ? false : seen.add(a.id)));
  }

  /** Marca como "Nuevo" lo que no estaba en el digest anterior que viste. */
  function computeNewIds(data, articles) {
    const seen = storage.get(KEYS.seen, null);
    const ids = articles.map((a) => a.id);
    if (!seen || !seen.current) {
      storage.set(KEYS.seen, { current: { at: data.generated_at, ids }, previous: null });
      return new Set();
    }
    let { current, previous } = seen;
    if (current.at !== data.generated_at) {
      previous = current;
      current = { at: data.generated_at, ids };
      storage.set(KEYS.seen, { current, previous });
    }
    if (!previous) return new Set();
    const before = new Set(previous.ids);
    return new Set(ids.filter((id) => !before.has(id)));
  }

  function applyDigest(data) {
    state.digest = data;
    state.all = normalizeArticles(data);
    state.newIds = computeNewIds(data, state.all);
    const validIds = new Set(state.all.map((a) => a.id));
    state.selected = new Set([...state.selected].filter((id) => validIds.has(id)));
    if (state.filters.category && !state.all.some((a) => a.category === state.filters.category)) state.filters.category = "";
    renderSourceOptions();
    renderAll();
    updateFreshness();
  }

  async function loadDigest({ quiet = false } = {}) {
    try {
      const data = await fetchDigest();
      if (!data) { renderWelcome(); updateFreshness(); return null; }
      applyDigest(data);
      if (!quiet) showToast(`${plural(state.all.length, "noticia cargada", "noticias cargadas")}`);
      return data;
    } catch (error) {
      if (!state.digest) renderError(error);
      else showToast("Sin conexión: se muestran las últimas noticias guardadas");
      return null;
    }
  }

  // ── Filtros y render ──────────────────────────────────────────────────────
  function filterArticles() {
    const { category, source, sensitive, sort, query } = state.filters;
    const q = normalize(query);
    const list = state.all.filter((a) => {
      if (category && a.category !== category) return false;
      if (source && a.source !== source) return false;
      if (sensitive === "yes" && !a.is_sensitive) return false;
      if (sensitive === "no" && a.is_sensitive) return false;
      if (q) {
        const hay = normalize([a.title, a.summary, a.source, a.category, ...a.matched_keywords].join(" "));
        if (!q.split(" ").every((word) => hay.includes(word))) return false;
      }
      return true;
    });
    list.sort((a, b) => {
      if (sort === "date") return articleDate(b) - articleDate(a) || b.score - a.score;
      if (sort === "source") return a.source.localeCompare(b.source, "es") || b.score - a.score;
      return b.score - a.score || articleDate(b) - articleDate(a);
    });
    state.filtered = list;
  }

  function renderAll() {
    filterArticles();
    renderTabs();
    renderStats();
    renderContent();
    renderStatus();
    renderSelection();
    renderFooter();
  }

  function renderTabs() {
    const counts = new Map();
    state.all.forEach((a) => counts.set(a.category, (counts.get(a.category) || 0) + 1));
    const cats = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const active = state.filters.category;
    els.tabs.innerHTML =
      `<button class="tab${active ? "" : " active"}" role="tab" data-category="">Todas <span class="tab-count">${state.all.length}</span></button>` +
      cats.map(([cat, n]) => `
        <button class="tab${active === cat ? " active" : ""}" role="tab" data-category="${esc(cat)}" style="--c:${colorFor(cat)}">
          <span class="tab-dot"></span>${esc(cat.charAt(0) + cat.slice(1).toLowerCase())} <span class="tab-count">${n}</span>
        </button>`).join("");
  }

  function renderSourceOptions() {
    const sources = [...new Set(state.all.map((a) => a.source))].sort((a, b) => a.localeCompare(b, "es"));
    if (state.filters.source && !sources.includes(state.filters.source)) state.filters.source = "";
    els.source.innerHTML = `<option value="">Todas las fuentes</option>` +
      sources.map((s) => `<option value="${esc(s)}"${s === state.filters.source ? " selected" : ""}>${esc(s)}</option>`).join("");
  }

  function renderStats() {
    const d = state.digest;
    if (!d) { els.stats.innerHTML = ""; return; }
    const sensitive = state.all.filter((a) => a.is_sensitive).length;
    const sourcesWithNews = new Set(state.all.map((a) => a.source)).size;
    const warnings = Number(d.sources_with_errors || 0);
    els.stats.innerHTML = `
      <div class="stat">
        <div class="stat-label">Noticias</div>
        <div class="stat-value">${state.filtered.length}</div>
        <div class="stat-note">${state.filtered.length === state.all.length ? "todas visibles" : `de ${state.all.length} en total`}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Nuevas</div>
        <div class="stat-value">${state.newIds.size}</div>
        <div class="stat-note">desde la última actualización</div>
      </div>
      <button class="stat" type="button" data-action="sensitive">
        <div class="stat-label">Sensibles</div>
        <div class="stat-value">${sensitive}</div>
        <div class="stat-note">${state.filters.sensitive === "yes" ? "mostrando solo sensibles" : "pulsa para revisarlas"}</div>
      </button>
      <button class="stat" type="button" data-action="sources">
        <div class="stat-label">Fuentes</div>
        <div class="stat-value">${sourcesWithNews}<span style="font-size:15px;color:var(--faint)">/${d.total_feeds || d.sources?.length || "—"}</span></div>
        <div class="stat-note${warnings ? " warn" : ""}">${warnings ? `${plural(warnings, "con aviso", "con aviso")} · ver detalle` : `últimas ${d.window_hours || 12} h · ver detalle`}</div>
      </button>`;
  }

  function renderStatus() {
    const n = state.filtered.length;
    const hasFilters = Boolean(state.filters.category || state.filters.source || state.filters.sensitive || state.filters.query);
    els.clearFilters.hidden = !hasFilters;
    els.selectAll.hidden = !n;
    const allSelected = n && state.filtered.every((a) => state.selected.has(a.id));
    els.selectAll.textContent = allSelected ? "Quitar selección" : "Seleccionar visibles";
    if (!state.digest) { els.status.textContent = ""; return; }
    els.status.innerHTML = hasFilters
      ? `<strong>${n}</strong> de ${state.all.length} noticias con los filtros actuales`
      : `<strong>${n}</strong> noticias, ordenadas por ${({ score: "relevancia", date: "fecha", source: "fuente" })[state.filters.sort]}`;
  }

  function renderContent() {
    if (!state.digest) return;
    if (!state.filtered.length) {
      els.content.innerHTML = `
        <div class="empty">
          <div class="empty-icon">🔎</div>
          <h3>No hay noticias con estos filtros</h3>
          <p>Prueba con otra búsqueda o quita los filtros para ver todo el digest.</p>
          <button class="btn btn-primary" type="button" data-action="clear-filters">Quitar filtros</button>
        </div>`;
      return;
    }
    // Agrupado por categoría en "Todas" y orden por relevancia; lista plana en el resto.
    const grouped = !state.filters.category && state.filters.sort === "score";
    if (!grouped) {
      els.content.innerHTML = `<div class="cards">${state.filtered.map(renderCard).join("")}</div>`;
      return;
    }
    const groups = new Map();
    state.filtered.forEach((a) => { if (!groups.has(a.category)) groups.set(a.category, []); groups.get(a.category).push(a); });
    els.content.innerHTML = [...groups.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .map(([cat, items]) => `
        <section class="section" style="--c:${colorFor(cat)}">
          <div class="section-head">
            <span class="dot"></span><h2>${esc(cat)}</h2><span class="count">${items.length}</span><span class="line"></span>
          </div>
          <div class="cards">${items.map(renderCard).join("")}</div>
        </section>`).join("");
  }

  function renderCard(a, index) {
    const color = colorFor(a.category);
    const selected = state.selected.has(a.id);
    const initial = esc(a.category.charAt(0));
    const media = a.image
      ? `<img src="${esc(a.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()"><div class="card-media-fallback">${initial}</div>`
      : `<div class="card-media-fallback">${initial}</div>`;
    const flags = [];
    if (a.is_sensitive) flags.push(`<span class="flag sensitive" title="${esc(a.sensitive_terms.join(", "))}">⚠ Sensible</span>`);
    if (a.needs_human_review && !a.is_sensitive) flags.push(`<span class="flag review">Revisión humana</span>`);
    if (a.recommended_format && a.recommended_format !== "Revisión humana") flags.push(`<span class="flag">${esc(a.recommended_format)}</span>`);
    const scorePct = Math.max(6, Math.min(100, a.score));
    return `
      <article class="card${selected ? " selected" : ""}" data-id="${esc(a.id)}" style="--c:${color};animation-delay:${Math.min(index, 12) * 25}ms">
        <a class="card-link" href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">
          <div class="card-media">
            ${media}
            <span class="card-tag">${esc(a.category)}</span>
            ${state.newIds.has(a.id) ? `<span class="card-new">NUEVO</span>` : ""}
          </div>
          <div class="card-body">
            <h3 class="card-title">${esc(a.title)}</h3>
            ${a.summary ? `<p class="card-summary">${esc(a.summary)}</p>` : ""}
            ${flags.length ? `<div class="card-flags">${flags.join("")}</div>` : ""}
            <div class="card-meta">
              <span class="src">${esc(a.source)}</span><span>·</span><span>${esc(shortDate(a))}</span>
              <span class="score" title="Relevancia ${a.score}"><span class="score-bar"><i style="width:${scorePct}%"></i></span>${a.score}</span>
            </div>
          </div>
        </a>
        <button class="card-check" type="button" aria-pressed="${selected}" aria-label="Seleccionar noticia">
          <svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>
        </button>
      </article>`;
  }

  function renderFooter() {
    const d = state.digest;
    const where = IS_DESKTOP ? "App de escritorio" : (IS_STANDALONE ? "App iPhone" : "Versión web");
    els.footer.innerHTML = `ac2ality · ${where}${d ? ` · ${d.total_feeds || ""} fuentes · ventana de ${d.window_hours || 12} h` : ""} · <button class="link-btn" type="button" data-action="help">Ayuda</button>`;
  }

  function renderWelcome() {
    state.digest = null;
    els.stats.innerHTML = "";
    els.tabs.innerHTML = "";
    els.status.textContent = "";
    els.content.innerHTML = `
      <div class="welcome">
        <div class="brand-logo">ac<span>2</span>ality</div>
        <h3>Bienvenida al digest de noticias</h3>
        <p>${IS_DESKTOP
          ? "Vamos a revisar ahora las fuentes de noticias para preparar tu primer digest. Tarda alrededor de medio minuto y podrás ver el progreso en todo momento."
          : "Todavía no hay noticias publicadas. En cuanto se genere el siguiente digest aparecerá aquí automáticamente."}</p>
        <button class="btn btn-primary" type="button" data-action="refresh">${IS_DESKTOP ? "Cargar noticias" : "Comprobar de nuevo"}</button>
      </div>`;
  }

  function renderError(error) {
    els.content.innerHTML = `
      <div class="empty">
        <div class="empty-icon">📡</div>
        <h3>No hemos podido cargar las noticias</h3>
        <p>${IS_DESKTOP ? "Comprueba la conexión a internet y vuelve a intentarlo." : "Parece que no hay conexión. Cuando vuelva, pulsa reintentar."}</p>
        <p style="margin-top:8px;font-size:12.5px;color:var(--faint)">${esc(error?.message || error)}</p>
        <button class="btn btn-primary" type="button" data-action="refresh">Reintentar</button>
      </div>`;
  }

  // ── Frescura ──────────────────────────────────────────────────────────────
  function digestAgeMinutes() {
    const at = Date.parse(state.digest?.generated_at || "");
    return Number.isNaN(at) ? Infinity : (Date.now() - at) / 60000;
  }

  function updateFreshness() {
    const el = els.freshness;
    el.classList.remove("fresh", "aging", "stale");
    if (state.job?.running) {
      els.freshnessText.textContent = "Actualizando noticias…";
      el.classList.add("aging");
      return;
    }
    if (!state.digest) { els.freshnessText.textContent = "Sin noticias todavía"; el.classList.add("stale"); return; }
    const age = digestAgeMinutes();
    const at = new Date(state.digest.generated_at);
    el.classList.add(age < 180 ? "fresh" : age < 480 ? "aging" : "stale");
    els.freshnessText.textContent = `Actualizado ${relativeTime(at)} · ${at.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}`;
  }

  // ── Selección ─────────────────────────────────────────────────────────────
  function toggleSelected(id) {
    state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
    const card = els.content.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
    if (card) {
      const on = state.selected.has(id);
      card.classList.toggle("selected", on);
      card.querySelector(".card-check")?.setAttribute("aria-pressed", String(on));
    }
    renderSelection();
    renderStatus();
  }

  function renderSelection() {
    const n = state.selected.size;
    els.actionBar.classList.toggle("visible", n > 0);
    document.body.classList.toggle("has-selection", n > 0);
    els.selectedCount.textContent = n;
    els.selectedLabel.textContent = n === 1 ? "seleccionada" : "seleccionadas";
  }

  function selectVisible() {
    const all = state.filtered.every((a) => state.selected.has(a.id));
    state.filtered.forEach((a) => (all ? state.selected.delete(a.id) : state.selected.add(a.id)));
    renderContent();
    renderSelection();
    renderStatus();
  }

  function clearSelection() {
    state.selected.clear();
    renderContent();
    renderSelection();
    renderStatus();
  }

  const selectedArticles = () => state.all.filter((a) => state.selected.has(a.id));

  // ── Exportar / guardar ───────────────────────────────────────────────────
  function toMarkdown(list, title = "Selección curada de noticias — AC2ALITY") {
    const now = new Date();
    const header = `# ${title}\n\n${plural(list.length, "noticia", "noticias")} · exportado el ${now.toLocaleString("es-ES")}\n`;
    const body = list.map((a, i) => [
      `## ${i + 1}. ${a.title}`, "",
      `- **Fuente:** ${a.source}`,
      `- **Fecha:** ${a.published_local || "sin fecha"}`,
      `- **Categoría:** ${a.category}`,
      `- **Relevancia:** ${a.score}`,
      `- **Sensible:** ${a.is_sensitive ? `Sí (${a.sensitive_terms.join(", ") || "sin detalle"})` : "No"}`,
      a.recommended_format ? `- **Formato recomendado:** ${a.recommended_format}` : null,
      `- **URL:** ${a.url}`, "",
      a.summary ? `${a.summary}\n` : null,
    ].filter((line) => line !== null).join("\n")).join("\n---\n\n");
    return `${header}\n${body}`;
  }

  function toPlainText(list) {
    return list.map((a, i) => `${i + 1}. ${a.title}\n${a.source} · ${a.published_local || "sin fecha"} · ${a.category}\n${a.url}`).join("\n\n");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement("textarea");
      area.value = text; area.style.position = "fixed"; area.style.opacity = "0";
      document.body.appendChild(area); area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  async function saveFile(filename, content, mime) {
    if (IS_DESKTOP) {
      try {
        const result = await api("/api/export", { method: "POST", body: JSON.stringify({ filename, content }) });
        showToast(`Guardado en Descargas: ${result.path.split(/[\\/]/).pop()}`, 3600);
      } catch (error) {
        showToast(`No se pudo guardar el archivo (${error.message})`);
      }
      return;
    }
    const blob = new Blob([content], { type: `${mime};charset=utf-8` });
    const file = new File([blob], filename, { type: mime });
    if (IS_IOS && navigator.canShare?.({ files: [file] })) {
      try { await navigator.share({ files: [file], title: filename }); return; } catch (e) { if (e.name === "AbortError") return; }
    }
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: filename });
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    showToast("Archivo descargado");
  }

  const stamp = () => new Date().toISOString().slice(0, 10);

  async function exportSelection(kind) {
    const list = selectedArticles();
    if (!list.length) return;
    if (kind === "copy") {
      showToast((await copyText(toPlainText(list))) ? `${plural(list.length, "noticia copiada", "noticias copiadas")}` : "No se pudo copiar");
    } else if (kind === "md") {
      await saveFile(`ac2ality-curacion-${stamp()}.md`, toMarkdown(list), "text/markdown");
    } else if (kind === "json") {
      const payload = { project: "ac2ality-curated-selection", exported_at: new Date().toISOString(), total_articles: list.length, articles: list };
      await saveFile(`ac2ality-curacion-${stamp()}.json`, JSON.stringify(payload, null, 2), "application/json");
    } else if (kind === "save") {
      const saved = storage.get(KEYS.saved, []);
      const byId = new Map(saved.map((a) => [a.id, a]));
      list.forEach((a) => byId.set(a.id, { ...a, saved_at: new Date().toISOString() }));
      storage.set(KEYS.saved, [...byId.values()]);
      updateSavedBadge();
      showToast(`${plural(list.length, "noticia guardada", "noticias guardadas")} · ábrelas desde el marcador`);
      clearSelection();
    }
  }

  function updateSavedBadge() {
    const n = storage.get(KEYS.saved, []).length;
    els.savedBadge.hidden = !n;
    els.savedBadge.textContent = n > 99 ? "99+" : n;
  }

  // ── Panel lateral ─────────────────────────────────────────────────────────
  function openDrawer(kind) {
    els.drawerOverlay.hidden = false;
    if (kind === "saved") renderSavedDrawer();
    else if (kind === "sources") renderSourcesDrawer();
    else renderHelpDrawer();
  }
  const closeDrawer = () => { els.drawerOverlay.hidden = true; };

  function renderSavedDrawer() {
    const saved = storage.get(KEYS.saved, []).sort((a, b) => String(b.saved_at).localeCompare(String(a.saved_at)));
    els.drawerTitle.textContent = `Guardadas (${saved.length})`;
    els.drawerBody.innerHTML = saved.length ? `
      <div class="drawer-actions" style="margin:0 0 8px">
        <button class="btn btn-ghost" type="button" data-action="saved-copy">Copiar todo</button>
        <button class="btn btn-ghost" type="button" data-action="saved-md">Markdown</button>
        <button class="btn btn-ghost" type="button" data-action="saved-clear" style="color:var(--danger)">Vaciar</button>
      </div>
      ${saved.map((a) => `
        <div class="saved-item">
          <a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">
            <strong>${esc(a.title)}</strong>
            <small>${esc(a.source)} · ${esc(a.category)} · guardada ${esc(a.saved_at ? relativeTime(new Date(a.saved_at)) : "")}</small>
          </a>
          <button type="button" data-action="saved-remove" data-id="${esc(a.id)}" aria-label="Quitar">✕</button>
        </div>`).join("")}`
      : `<div class="tip">Aún no has guardado noticias. Marca el círculo de cualquier tarjeta y pulsa <strong>Guardar</strong>: quedarán aquí aunque el digest se actualice.</div>`;
  }

  function renderSourcesDrawer() {
    const d = state.digest;
    els.drawerTitle.textContent = "Estado de las fuentes";
    if (!d) { els.drawerBody.innerHTML = `<div class="tip">Todavía no hay digest.</div>`; return; }
    const counts = new Map();
    state.all.forEach((a) => counts.set(a.source, (counts.get(a.source) || 0) + 1));
    const rows = (d.sources || d.source_summary || []).map((s) => ({ name: s.name, n: counts.get(s.name) || 0, error: s.error }));
    rows.sort((a, b) => b.n - a.n || a.name.localeCompare(b.name, "es"));
    const withNews = rows.filter((r) => r.n), without = rows.filter((r) => !r.n);
    const row = (r) => `
      <div class="source-row">
        <div class="name">${esc(r.name)}${r.error ? `<span class="warn-text">⚠ ${esc(r.error)}</span>` : ""}</div>
        <span class="n">${r.n}</span>
      </div>`;
    els.drawerBody.innerHTML = `
      <div class="tip">Generado el <strong>${esc(new Date(d.generated_at).toLocaleString("es-ES"))}</strong>. Se revisan ${d.total_feeds || rows.length} fuentes y se guardan las noticias de las últimas ${d.window_hours || 12} horas (${d.total_articles_raw || "—"} encontradas, ${d.total_articles || state.all.length} tras quitar duplicados).</div>
      <div class="drawer-section"><h3>Con noticias (${withNews.length})</h3>${withNews.map(row).join("")}</div>
      ${without.length ? `<div class="drawer-section"><h3>Sin noticias relevantes ahora (${without.length})</h3>${without.map(row).join("")}</div>` : ""}`;
  }

  function renderHelpDrawer() {
    els.drawerTitle.textContent = "Ayuda";
    const install = IS_DESKTOP ? "" : `
      <div class="drawer-section">
        <h3>Instalar en el iPhone</h3>
        <div class="tip">${IS_STANDALONE ? "✅ Ya la estás usando como app." :
          "Abre esta página en <strong>Safari</strong>, pulsa <strong>Compartir</strong> (el cuadrado con la flecha) y elige <strong>Añadir a pantalla de inicio</strong>. Tendrás el icono de ac2ality y se abrirá a pantalla completa, también sin conexión."}</div>
      </div>`;
    els.drawerBody.innerHTML = `
      ${install}
      <div class="drawer-section">
        <h3>Actualizar noticias</h3>
        <div class="tip">${IS_DESKTOP
          ? "Pulsa <strong>Actualizar</strong> arriba a la derecha. Verás cómo se consulta cada fuente en directo; puedes seguir leyendo mientras tanto. Si abres la app y las noticias tienen más de 2 horas, se actualizan solas."
          : "Las noticias se generan automáticamente varias veces al día. Pulsa <strong>Actualizar</strong> para traer la última versión publicada."}</div>
      </div>
      <div class="drawer-section">
        <h3>Seleccionar y exportar</h3>
        <div class="tip">Toca el círculo de una tarjeta para seleccionarla. Abajo aparecerán las opciones: <strong>Copiar</strong>, <strong>Guardar</strong> (para consultarlas luego desde el marcador), <strong>Markdown</strong> o <strong>JSON</strong>.</div>
      </div>
      <div class="drawer-section">
        <h3>Atajos de teclado</h3>
        <div class="tip"><strong>/</strong> buscar · <strong>R</strong> actualizar · <strong>Esc</strong> cerrar o quitar selección</div>
      </div>`;
  }

  // ── Actualización (escritorio: en directo · web: última publicada) ──────
  async function startRefresh() {
    if (!IS_DESKTOP) return refreshWeb();
    if (state.job?.running) { showOverlay(); return; }
    try {
      state.overlayMinimized = false;
      const job = await api("/api/refresh", { method: "POST", body: "{}" });
      attachToJob(job);
    } catch (error) {
      showToast(`No se pudo iniciar la actualización (${error.message})`);
    }
  }

  async function refreshWeb() {
    setRefreshBusy(true, "Comprobando…");
    const before = state.digest?.generated_at;
    const data = await loadDigest({ quiet: true });
    setRefreshBusy(false);
    if (!data) return;
    if (data.generated_at === before) showToast("Ya tienes la última versión publicada");
    else showToast(state.newIds.size ? `${plural(state.newIds.size, "noticia nueva", "noticias nuevas")}` : "Digest actualizado");
  }

  function setRefreshBusy(busy, label) {
    els.refreshBtn.classList.toggle("busy", busy);
    els.refreshBtn.disabled = busy && !IS_DESKTOP;
    els.refreshLabel.textContent = busy ? (label || "Actualizando…") : "Actualizar";
  }

  function attachToJob(job) {
    state.job = job;
    state.jobStartedAt = Date.parse(job.started_at || "") || Date.now();
    buildSourceGrid(job.sources);
    if (!state.overlayMinimized) showOverlay();
    setRefreshBusy(true);
    renderJob(job);
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(pollJob, 300);
  }

  async function pollJob() {
    try {
      const job = await api("/api/status");
      state.job = job;
      renderJob(job);
      if (!job.running) {
        clearInterval(state.pollTimer);
        await finishJob(job);
      }
    } catch { /* el siguiente sondeo lo reintentará */ }
  }

  function buildSourceGrid(sources) {
    els.sourceGrid.innerHTML = sources.map((s, i) =>
      `<div class="src-pill" data-i="${i}" title="${esc(s.name)}"><i></i><span class="name">${esc(s.name)}</span><span class="n"></span></div>`).join("");
  }

  function renderJob(job) {
    const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
    const shown = job.phase === "processing" ? 100 : pct;
    const circumference = 326.73;
    els.ringFill.style.strokeDashoffset = String(circumference * (1 - (job.phase === "done" ? 1 : shown / 100)));
    els.ringValue.textContent = `${shown}%`;
    els.ring.classList.toggle("processing", job.phase === "processing");
    els.ring.classList.toggle("done", job.phase === "done");
    els.ring.classList.toggle("error", job.phase === "error");

    const elapsed = Math.max(0, Math.round((Date.now() - state.jobStartedAt) / 1000));
    els.rcSources.textContent = `${job.done}/${job.total}`;
    els.rcArticles.textContent = job.phase === "done" ? job.total_articles : job.articles_so_far;
    els.rcTime.textContent = `${elapsed} s`;
    els.rcArticles.nextElementSibling.textContent = job.phase === "done" ? "noticias en el digest" : "noticias halladas";

    const loading = job.sources.filter((s) => s.state === "loading").map((s) => s.name);
    if (job.phase === "fetching") {
      els.refreshTitle.textContent = "Buscando noticias";
      els.refreshSub.textContent = loading.length ? `Consultando ${loading.slice(0, 2).join(", ")}${loading.length > 2 ? ` y ${loading.length - 2} más` : ""}…` : "Conectando con las fuentes…";
    } else if (job.phase === "processing") {
      els.refreshTitle.textContent = "Ordenando el digest";
      els.refreshSub.textContent = "Clasificando por categorías y quitando duplicados…";
    } else if (job.phase === "done") {
      els.refreshTitle.textContent = "¡Noticias listas!";
      els.refreshSub.textContent = `${plural(job.total_articles, "noticia", "noticias")} en ${elapsed} s${job.sources_with_errors ? ` · ${job.sources_with_errors} fuentes con aviso` : ""}`;
    } else if (job.phase === "error") {
      els.refreshTitle.textContent = "No se pudo completar";
      els.refreshSub.textContent = job.error || "Revisa la conexión a internet e inténtalo de nuevo.";
    }

    const order = ["fetch", "process", "done"];
    const current = { fetching: 0, processing: 1, done: 3, error: -1 }[job.phase] ?? 0;
    els.steps.querySelectorAll("li").forEach((li) => {
      const i = order.indexOf(li.dataset.step);
      li.classList.toggle("done", i < current);
      li.classList.toggle("active", i === current);
    });

    job.sources.forEach((s, i) => {
      const pill = els.sourceGrid.children[i];
      if (!pill) return;
      const cls = s.state === "done" && !s.count ? "empty" : s.state;
      if (pill.dataset.state !== cls) {
        pill.className = `src-pill ${cls}`;
        pill.dataset.state = cls;
        pill.querySelector(".n").textContent = s.state === "done" || s.state === "warning" ? (s.count || (s.state === "warning" ? "!" : "0")) : "";
        if (s.error) pill.title = `${s.name}: ${s.error}`;
      }
    });

    els.miniFill.style.width = `${shown}%`;
    els.miniText.textContent = job.phase === "processing" ? "Ordenando…" : `${job.done}/${job.total} fuentes · ${job.articles_so_far} noticias`;
    els.miniProgress.hidden = !(job.running && state.overlayMinimized);
    els.refreshCloseBtn.hidden = job.running;
    els.minimizeBtn.hidden = !job.running;
    els.refreshCloseBtn.textContent = job.phase === "error" ? "Cerrar" : "Ver noticias";
    updateFreshness();
  }

  async function finishJob(job) {
    setRefreshBusy(false);
    els.miniProgress.hidden = true;
    if (job.phase === "done") {
      await loadDigest({ quiet: true });
      const nuevos = state.newIds.size;
      showToast(nuevos ? `✓ ${plural(nuevos, "noticia nueva", "noticias nuevas")}` : "✓ Digest actualizado", 3200);
      if (!els.overlay.hidden) setTimeout(() => { if (!state.job?.running) hideOverlay(); }, 1800);
    } else {
      showOverlay();
    }
    updateFreshness();
  }

  function showOverlay() {
    state.overlayMinimized = false;
    els.overlay.hidden = false;
    els.miniProgress.hidden = true;
  }
  function hideOverlay() { els.overlay.hidden = true; }
  function minimizeOverlay() {
    state.overlayMinimized = true;
    hideOverlay();
    if (state.job?.running) els.miniProgress.hidden = false;
  }

  // ── Tema y vista ──────────────────────────────────────────────────────────
  function applyTheme(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
  }
  function toggleTheme() {
    const current = document.documentElement.dataset.theme
      || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    storage.set(KEYS.theme, next);
  }
  function setView(view) {
    document.body.classList.toggle("view-list", view === "list");
    document.querySelectorAll("[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    storage.set(KEYS.view, view);
  }

  // ── Eventos ───────────────────────────────────────────────────────────────
  function bindEvents() {
    els.refreshBtn.addEventListener("click", startRefresh);
    els.themeBtn.addEventListener("click", toggleTheme);
    els.savedBtn.addEventListener("click", () => openDrawer("saved"));
    els.freshness.addEventListener("click", () => (state.job?.running ? showOverlay() : openDrawer("sources")));
    els.miniProgress.addEventListener("click", showOverlay);
    els.minimizeBtn.addEventListener("click", minimizeOverlay);
    els.refreshCloseBtn.addEventListener("click", hideOverlay);
    els.drawerClose.addEventListener("click", closeDrawer);
    els.drawerOverlay.addEventListener("click", (e) => { if (e.target === els.drawerOverlay) closeDrawer(); });
    els.overlay.addEventListener("click", (e) => { if (e.target === els.overlay) (state.job?.running ? minimizeOverlay() : hideOverlay()); });

    let searchTimer;
    els.search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.filters.query = els.search.value; renderAll(); }, 120);
    });
    els.sort.addEventListener("change", () => { state.filters.sort = els.sort.value; renderAll(); });
    els.source.addEventListener("change", () => { state.filters.source = els.source.value; renderAll(); });
    document.querySelectorAll("[data-sensitive]").forEach((btn) => btn.addEventListener("click", () => setSensitive(btn.dataset.sensitive)));
    document.querySelectorAll("[data-view]").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
    els.tabs.addEventListener("click", (e) => {
      const tab = e.target.closest(".tab");
      if (!tab) return;
      state.filters.category = tab.dataset.category;
      renderAll();
      tab.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    els.selectAll.addEventListener("click", selectVisible);
    els.clearFilters.addEventListener("click", clearFilters);

    $("copy-btn").addEventListener("click", () => exportSelection("copy"));
    $("save-btn").addEventListener("click", () => exportSelection("save"));
    $("md-btn").addEventListener("click", () => exportSelection("md"));
    $("json-btn").addEventListener("click", () => exportSelection("json"));
    $("deselect-btn").addEventListener("click", clearSelection);

    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onKey);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) updateFreshness(); });
  }

  function setSensitive(value) {
    state.filters.sensitive = value;
    document.querySelectorAll("[data-sensitive]").forEach((b) => b.classList.toggle("active", b.dataset.sensitive === value));
    renderAll();
  }

  function clearFilters() {
    state.filters = { ...state.filters, category: "", source: "", sensitive: "", query: "" };
    els.search.value = "";
    els.source.value = "";
    setSensitive("");
  }

  async function onDocumentClick(e) {
    const check = e.target.closest(".card-check");
    if (check) { e.preventDefault(); toggleSelected(check.closest(".card").dataset.id); return; }

    const action = e.target.closest("[data-action]");
    if (action) {
      const kind = action.dataset.action;
      if (kind === "refresh") return IS_DESKTOP ? startRefresh() : refreshWeb();
      if (kind === "clear-filters") return clearFilters();
      if (kind === "sources") return openDrawer("sources");
      if (kind === "help") return openDrawer("help");
      if (kind === "sensitive") return setSensitive(state.filters.sensitive === "yes" ? "" : "yes");
      if (kind === "saved-remove") {
        storage.set(KEYS.saved, storage.get(KEYS.saved, []).filter((a) => a.id !== action.dataset.id));
        updateSavedBadge(); return renderSavedDrawer();
      }
      if (kind === "saved-copy") return showToast((await copyText(toPlainText(storage.get(KEYS.saved, [])))) ? "Guardadas copiadas" : "No se pudo copiar");
      if (kind === "saved-md") return saveFile(`ac2ality-guardadas-${stamp()}.md`, toMarkdown(storage.get(KEYS.saved, []), "Noticias guardadas — AC2ALITY"), "text/markdown");
      if (kind === "saved-clear") {
        if (confirm("¿Vaciar todas las noticias guardadas?")) { storage.set(KEYS.saved, []); updateSavedBadge(); renderSavedDrawer(); }
        return;
      }
    }

    // En la app de escritorio los enlaces se abren en el navegador del sistema.
    const link = e.target.closest('a[href^="http"]');
    if (link && IS_DESKTOP) {
      e.preventDefault();
      api("/api/open", { method: "POST", body: JSON.stringify({ url: link.href }) }).catch(() => window.open(link.href, "_blank"));
    }
  }

  function onKey(e) {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "");
    if (e.key === "Escape") {
      if (!els.drawerOverlay.hidden) return closeDrawer();
      if (!els.overlay.hidden) return state.job?.running ? minimizeOverlay() : hideOverlay();
      if (typing && els.search.value) { els.search.value = ""; state.filters.query = ""; return renderAll(); }
      if (state.selected.size) return clearSelection();
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); els.search.focus(); }
    if (e.key.toLowerCase() === "r") startRefresh();
  }

  // ── Arranque ──────────────────────────────────────────────────────────────
  async function boot() {
    applyTheme(storage.get(KEYS.theme, null));
    setView(storage.get(KEYS.view, "grid"));
    bindEvents();
    updateSavedBadge();
    renderFooter();
    if (!IS_DESKTOP) els.refreshBtn.title = "Traer la última versión publicada";

    await loadDigest({ quiet: true });

    if (IS_DESKTOP) {
      try {
        const job = await api("/api/status");
        if (job.running) attachToJob(job);                       // ya había una en marcha
        else if (!state.digest || digestAgeMinutes() > AUTO_REFRESH_AFTER_MIN) startRefresh();
      } catch { /* sin API: modo lectura */ }
      // Latido para que la app sepa que la ventana sigue abierta (modo navegador).
      setInterval(() => { if (!state.job?.running) fetch("/api/status", { cache: "no-store" }).catch(() => {}); }, 20000);
    } else {
      if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
        navigator.serviceWorker.register("sw.js").catch(() => {});
      }
      // Al volver a la app en el iPhone, trae la última versión si ha pasado un rato.
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden && digestAgeMinutes() > 30) loadDigest({ quiet: true });
      });
    }

    setInterval(updateFreshness, 60000);
  }

  boot();
})();
