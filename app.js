const state = {
  dates: [],
  currentDate: null,
  items: [],
  activeSource: null, // null = tous
  activeTags: new Set(),
};

const els = {
  dateSelect: document.getElementById("date-select"),
  heroDate: document.getElementById("hero-date"),
  heroSub: document.getElementById("hero-sub"),
  sourceFilters: document.getElementById("source-filters"),
  tagFilters: document.getElementById("tag-filters"),
  grid: document.getElementById("grid"),
  emptyState: document.getElementById("empty-state"),
  modal: document.getElementById("detail-modal"),
  modalBody: document.getElementById("modal-body"),
  modalClose: document.getElementById("modal-close"),
};

const SOURCE_LABELS = { reddit: "Reddit", youtube: "YouTube", rss: "Blog" };

// --- Gestion de la modale ---
function initModal() {
  if (!els.modal) return;
  
  const closeModal = () => els.modal.setAttribute("hidden", "true");

  els.modalClose.addEventListener("click", closeModal);
  els.modal.addEventListener("click", (e) => {
    if (e.target === els.modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

function openModal(item) {
  if (!els.modal || !els.modalBody) return;

  let mediaHtml = "";
  if (item.thumbnail) {
    mediaHtml = `<img src="${escapeHtml(item.thumbnail)}" alt="" class="modal-thumb">`;
  } else {
    const hue = hashHue(item.source_name || item.source || "veille");
    mediaHtml = `
      <div class="card-media placeholder" style="background: linear-gradient(135deg, hsl(${hue} 70% 45%), hsl(${(hue + 40) % 360} 70% 35%)); margin-bottom: 16px; border-radius: var(--radius); min-height: 200px; display: flex; align-items: center; justify-content: center;">
        <span class="initial" style="font-family: var(--font-display); font-weight: 700; font-size: 2.5rem; color: rgba(255,255,255,0.85);">${(item.source_name || "?").trim().charAt(0).toUpperCase()}</span>
      </div>
    `;
  }

  const sourceName = item.source_name || SOURCE_LABELS[item.source] || item.source || "";
  const tagsList = (item.tags || []).map(t => `<span>${escapeHtml(t)}</span>`).join("");
  const targetUrl = item.external_url || item.url || "#";

  els.modalBody.innerHTML = `
    ${mediaHtml}
    <span class="source-pill" style="position:static; display:inline-block; margin-bottom:12px;">${escapeHtml(sourceName)}</span>
    <h2>${escapeHtml(item.title)}</h2>
    <p>${escapeHtml(item.summary_fr || item.raw_summary || "Aucun résumé disponible.")}</p>
    <div class="modal-footer-action" style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--line); padding-top: 16px; flex-wrap: wrap; gap: 12px;">
      <div class="card-tags">${tagsList}</div>
      <a href="${escapeHtml(targetUrl)}" target="_blank" rel="noopener noreferrer" class="external-btn">Voir l'original →</a>
    </div>
  `;

  els.modal.removeAttribute("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/[&<>'"]/g, 
    tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
  );
}

init();

async function init() {
  initModal();

  try {
    const res = await fetch("data/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error("index.json introuvable");
    state.dates = await res.json();
  } catch (e) {
    state.dates = [];
  }

  if (state.dates.length === 0) {
    els.heroDate.textContent = "Pas encore de veille";
    els.heroSub.textContent = "Le premier scan automatique n'a pas encore tourné. Revenez demain, ou lancez le workflow manuellement depuis l'onglet Actions du dépôt.";
    els.emptyState.hidden = true;
    return;
  }

  populateDateSelect();
  await loadDate(state.dates[0]);

  els.dateSelect.addEventListener("change", (e) => loadDate(e.target.value));
}

function populateDateSelect() {
  els.dateSelect.innerHTML = "";
  for (const d of state.dates) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = formatDateLong(d);
    els.dateSelect.appendChild(opt);
  }
}

async function loadDate(dateStr) {
  state.currentDate = dateStr;
  els.dateSelect.value = dateStr;
  state.activeSource = null;
  state.activeTags = new Set();

  let items = [];
  try {
    const res = await fetch(`data/${dateStr}.json`, { cache: "no-store" });
    if (res.ok) items = await res.json();
  } catch (e) {
    items = [];
  }
  state.items = items;

  renderHero();
  renderFilters();
  renderGrid();
}

function renderHero() {
  els.heroDate.textContent = formatDateLong(state.currentDate);
  const n = state.items.length;
  if (n === 0) {
    els.heroSub.textContent = "Aucune trouvaille ce jour-là.";
    return;
  }
  const topTags = topN(countTags(state.items), 3).map(([t]) => t);
  const suffix = topTags.length ? ` · ${topTags.join(", ")}` : "";
  els.heroSub.textContent = `${n} trouvaille${n > 1 ? "s" : ""}${suffix}`;
}

function renderFilters() {
  const sources = [...new Set(state.items.map((it) => it.source))];
  els.sourceFilters.innerHTML = "";
  els.sourceFilters.appendChild(makeChip("Tous", state.activeSource === null, () => {
    state.activeSource = null;
    renderFilters();
    renderGrid();
  }));
  for (const src of sources) {
    const chip = makeChip(SOURCE_LABELS[src] || src, state.activeSource === src, () => {
      state.activeSource = state.activeSource === src ? null : src;
      renderFilters();
      renderGrid();
    });
    els.sourceFilters.appendChild(chip);
  }

  const tagCounts = countTags(state.items);
  const tags = topN(tagCounts, 12).map(([t]) => t);
  els.tagFilters.innerHTML = "";
  for (const tag of tags) {
    const chip = makeChip(tag, state.activeTags.has(tag), () => {
      if (state.activeTags.has(tag)) state.activeTags.delete(tag);
      else state.activeTags.add(tag);
      renderFilters();
      renderGrid();
    });
    chip.classList.add("tag-chip");
    els.tagFilters.appendChild(chip);
  }
}

function makeChip(label, active, onClick) {
  const btn = document.createElement("button");
  btn.className = "chip" + (active ? " active" : "");
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function renderGrid() {
  const filtered = state.items.filter((it) => {
    if (state.activeSource && it.source !== state.activeSource) return false;
    if (state.activeTags.size > 0) {
      const itemTags = new Set(it.tags || []);
      const hasOne = [...state.activeTags].some((t) => itemTags.has(t));
      if (!hasOne) return false;
    }
    return true;
  });

  els.grid.innerHTML = "";
  els.emptyState.hidden = filtered.length > 0;

  for (const it of filtered) {
    els.grid.appendChild(renderCard(it));
  }
}

function renderCard(item) {
  // On utilise un article cliquable au lieu d'un lien direct
  const article = document.createElement("article");
  article.className = "card";
  article.style.cursor = "pointer";

  const media = document.createElement("div");
  let mediaEl;
  if (item.thumbnail) {
    media.className = "card-media";
    const img = document.createElement("img");
    img.src = item.thumbnail;
    img.loading = "lazy";
    img.alt = "";
    img.onerror = () => { media.replaceWith(placeholderMedia(item)); };
    media.appendChild(img);
    mediaEl = media;
  } else {
    mediaEl = placeholderMedia(item);
  }

  const pill = document.createElement("span");
  pill.className = "source-pill";
  pill.textContent = item.source_name || SOURCE_LABELS[item.source] || item.source;
  mediaEl.appendChild(pill);

  const body = document.createElement("div");
  body.className = "card-body";

  const title = document.createElement("p");
  title.className = "card-title";
  title.textContent = item.title;
  body.appendChild(title);

  if (item.summary_fr) {
    const summary = document.createElement("p");
    summary.className = "card-summary";
    summary.textContent = item.summary_fr;
    body.appendChild(summary);
  }

  const footer = document.createElement("div");
  footer.className = "card-footer";

  const tagsWrap = document.createElement("div");
  tagsWrap.className = "card-tags";
  for (const tag of (item.tags || []).slice(0, 3)) {
    const span = document.createElement("span");
    span.textContent = tag;
    tagsWrap.appendChild(span);
  }
  footer.appendChild(tagsWrap);

  body.appendChild(footer);

  article.appendChild(mediaEl);
  article.appendChild(body);

  // Ouverture de la modale au clic
  article.addEventListener("click", () => {
    openModal(item);
  });

  return article;
}

function placeholderMedia(item) {
  const div = document.createElement("div");
  div.className = "card-media placeholder";
  const hue = hashHue(item.source_name || item.source || "veille");
  div.style.background = `linear-gradient(135deg, hsl(${hue} 70% 45%), hsl(${(hue + 40) % 360} 70% 35%))`;
  const initial = document.createElement("span");
  initial.className = "initial";
  initial.textContent = (item.source_name || "?").trim().charAt(0).toUpperCase();
  div.appendChild(initial);
  return div;
}

function countTags(items) {
  const counts = {};
  for (const it of items) {
    for (const t of (it.tags || [])) {
      counts[t] = (counts[t] || 0) + 1;
    }
  }
  return counts;
}

function topN(countsObj, n) {
  return Object.entries(countsObj).sort((a, b) => b[1] - (b[1] || 0)).slice(0, n);
}

function hashHue(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % 360;
}

function formatDateLong(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  const s = d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}
