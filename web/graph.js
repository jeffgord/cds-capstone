// Book graph page. Loads the precomputed variants from graph-data/ (built by graph/export.py) and drives
// two GraphViews (graph-draw.js). The URL (?model=&measure=&arrange=lcc&compare=1&book=) is the single
// source of truth for what's on screen.

const DATA = "graph-data/";
const LCC_FILE = "lcc-itself-reference";
const N_COLORS = 12; // the 12 biggest classes get a colour token each, the rest share --class-other
const SCORES = [
  ["p10_class", "of nearest books share the LoC class"],
  ["p10_sub", "share the LoC subclass"],
  ["nmi", "community match with LoC classes (NMI)"],
];

const $ = (id) => document.getElementById(id);
const state = { index: null, graphs: {}, hover: -1, highlight: "", colorOf: {}, colorVar: {} };

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  Object.assign(el, props);
  el.append(...kids.flat().filter((k) => k != null && k !== false));
  return el;
}

// ---- URL state ----
function params() {
  const p = new URLSearchParams(location.search);
  const book = state.index?.books.findIndex((b) => String(b.id) === p.get("book")) ?? -1;
  return { model: p.get("model") || "", measure: p.get("measure") || "", arrange: p.get("arrange") || "",
           compare: p.get("compare") === "1", book };
}

function setParams(next, { animate = true } = {}) {
  const p = { ...params(), ...next };
  const q = new URLSearchParams();
  if (p.model) q.set("model", p.model);
  if (p.measure) q.set("measure", p.measure);
  if (p.arrange) q.set("arrange", p.arrange);
  if (p.compare) q.set("compare", "1");
  if (p.book >= 0) q.set("book", state.index.books[p.book].id);
  history.replaceState(null, "", `${location.pathname}?${q}`);
  render(animate);
}

// ---- data ----
async function loadGraph(file) {
  state.graphs[file] ||= await (await fetch(`${DATA}${file}.json`)).json();
  return state.graphs[file];
}

function current() {
  const { model, measure } = params();
  const all = state.index.variants.filter((v) => v.file !== LCC_FILE);
  const models = [...new Set(all.map((v) => v.model))];
  const m = models.includes(model) ? model : models[0];
  const options = all.filter((v) => v.model === m);
  return { models, model: m, options, variant: options.find((v) => v.measure === measure) || options[0] };
}

const book = (i) => state.index.books[i];
const classOf = (i) => book(i).classes[0] || "";
const className = (c) => state.index.classes[c] || c;
// Short names for map labels: "Philosophy. Psychology. Religion" -> "Philosophy",
// "World History and History of Europe" -> "World History".
const shortName = (c) => className(c).split(". ")[0].split(" and ")[0];

// ---- views ----
const viewOpts = {
  colorOf: (i) => state.colorOf[classOf(i)] || state.colorOf[""],
  classOf,
  titleOf: (i) => book(i).title,
  classLabel: shortName,
  linkedState: () => ({ hover: state.hover, selected: params().book, highlight: state.highlight }),
  onHover(i, e) {
    if (i !== state.hover) {
      state.hover = i;
      drawAll();
    }
    showTip(i, e);
  },
  onSelect(i) {
    setParams({ book: i === params().book ? -1 : i }, { animate: false });
  },
};
const views = { main: new GraphView($("canvas-main"), viewOpts), lcc: new GraphView($("canvas-lcc"), viewOpts) };

function drawAll() {
  views.main.draw();
  if (params().compare) views.lcc.draw();
}

function showTip(i, e) {
  let tip = $("tip");
  if (!tip) tip = document.body.appendChild(h("div", { id: "tip", className: "graph-tip", hidden: true }));
  if (i < 0 || params().book >= 0) {
    tip.hidden = true;
    return;
  }
  tip.replaceChildren(h("strong", { textContent: book(i).title }),
    h("span", { textContent: book(i).author || "" }),
    h("span", { textContent: book(i).classes.map((c) => `${className(c)} (${c})`).join(", ") || "No LoC class" }));
  tip.hidden = false;
  tip.style.left = `${Math.min(e.pageX + 14, document.documentElement.clientWidth - tip.offsetWidth - 8)}px`;
  tip.style.top = `${e.pageY + 14}px`;
}

// ---- controls ----
function renderControls(cur) {
  const p = params();
  $("model").replaceChildren(...cur.models.map((m) => h("option", { value: m, textContent: m, selected: m === cur.model })));
  $("measure").replaceChildren(...cur.options.map((v) =>
    h("option", { value: v.measure, textContent: v.measure, selected: v === cur.variant })));
  $("measure").disabled = cur.options.length < 2;
  $("arrange-model").setAttribute("aria-pressed", String(p.arrange !== "lcc"));
  $("arrange-lcc").setAttribute("aria-pressed", String(p.arrange === "lcc"));
  $("compare").setAttribute("aria-pressed", String(p.compare));
  $("compare").classList.toggle("is-active", p.compare);
  $("view-lcc").hidden = !p.compare;
  $("stage").classList.toggle("is-split", p.compare);
  $("kicker-main").textContent = p.arrange === "lcc" ? "Arranged by LoC classes, linked by" : "Arranged and linked by";
  $("caption-main").textContent = `${cur.variant.model} · ${cur.variant.measure}`;
}

function wireControls() {
  $("model").addEventListener("change", (e) => setParams({ model: e.target.value, measure: "" }));
  $("measure").addEventListener("change", (e) => setParams({ measure: e.target.value }));
  $("arrange-model").addEventListener("click", () => setParams({ arrange: "" }));
  $("arrange-lcc").addEventListener("click", () => setParams({ arrange: "lcc" }));
  $("compare").addEventListener("click", () => setParams({ compare: !params().compare }, { animate: false }));
  $("controls").addEventListener("submit", (e) => e.preventDefault());
  $("find").addEventListener("change", (e) => {
    const i = state.index.books.findIndex((b) => b.title === e.target.value);
    if (i >= 0) {
      setParams({ book: i }, { animate: false });
      views.main.focusOn(i);
    }
  });
  document.querySelectorAll("[data-zoom]").forEach((btn) => btn.addEventListener("click", () => {
    const z = btn.dataset.zoom;
    if (z === "reset") views.main.reset();
    else views.main.zoomBy(z === "in" ? 1.5 : 1 / 1.5);
  }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && params().book >= 0) setParams({ book: -1 }, { animate: false });
  });
  $("titles").replaceChildren(...state.index.books.map((b) => h("option", { value: b.title })));
}

// ---- side panel ----
function dot(c) {
  const el = h("span", { className: "graph-dot" });
  el.style.background = `var(${state.colorVar[c] || "--class-other"})`;
  return el;
}

function renderOverview(variant) {
  const ref = state.index.variants.find((v) => v.file === LCC_FILE)?.scores || {};
  const counts = {};
  for (const b of state.index.books) for (const c of b.classes) counts[c] = (counts[c] || 0) + 1;
  const order = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  return [
    h("h2", { className: "graph-side-head", textContent: "How close to LoC?" }),
    h("ul", { className: "graph-meters" }, SCORES.filter(([k]) => variant.scores[k] != null).map(([k, text]) => {
      const fill = h("span", { className: "graph-meter-fill" });
      fill.style.width = `${(variant.scores[k] / (ref[k] || 1)) * 100}%`;
      return h("li", {},
        h("span", { className: "graph-meter-value", textContent: `${Math.round(variant.scores[k] * 100)}%` }),
        h("span", { className: "graph-meter-text", textContent: ` ${text}` }),
        h("span", { className: "graph-meter" }, fill),
        h("span", { className: "graph-meter-ref", textContent: `LoC itself: ${Math.round((ref[k] || 0) * 100)}%` }));
    })),
    h("h2", { className: "graph-side-head", textContent: "LoC classes" }),
    h("ul", { className: "graph-legend" }, order.map((c) => {
      const btn = h("button", { type: "button", className: "graph-legend-item", ariaPressed: String(state.highlight === c) },
        dot(c), h("span", { textContent: `${className(c)} (${c})` }), h("span", { className: "graph-count", textContent: counts[c] }));
      btn.addEventListener("click", () => {
        state.highlight = state.highlight === c ? "" : c;
        renderSide();
        drawAll();
      });
      return h("li", {}, btn);
    })),
  ];
}

function renderBook(i, variant) {
  const b = book(i);
  const nb = state.graphs[variant.file].nb[i];
  const lccNb = new Set(state.graphs[LCC_FILE]?.nb[i] || []);
  const shared = (j) => book(j).classes.some((c) => b.classes.includes(c));
  const sameClass = nb.filter(shared).length;
  const agree = nb.filter((j) => lccNb.has(j)).length;
  const img = h("img", { src: b.cover, alt: "", loading: "lazy" });
  img.addEventListener("error", () => img.replaceWith(h("span", { className: "graph-cover-fallback", textContent: b.title[0] })));
  const list = nb.map((j) => {
    const btn = h("button", { type: "button", className: "graph-nb" }, dot(classOf(j)),
      h("span", { className: "graph-nb-title", textContent: book(j).title }),
      shared(j) ? h("span", { className: "graph-nb-same", textContent: "same class", title: "Shares an LoC class" }) : null);
    btn.addEventListener("click", () => {
      setParams({ book: j }, { animate: false });
      views.main.focusOn(j);
    });
    return h("li", {}, btn);
  });
  const close = h("button", { type: "button", className: "graph-close", ariaLabel: "Close", textContent: "×" });
  close.addEventListener("click", () => setParams({ book: -1 }, { animate: false }));
  return [
    h("div", { className: "graph-book" }, h("div", { className: "graph-cover" }, img),
      h("div", {}, h("h2", { className: "graph-book-title", textContent: b.title }),
        h("p", { className: "graph-book-author", textContent: b.author || "" }),
        h("p", { className: "graph-book-classes" }, b.classes.map((c) => h("span", { className: "chip chip-class" }, dot(c), ` ${className(c)} (${c})`))),
        h("a", { className: "graph-open", href: `./?book=${b.id}`, textContent: "Open in search →" })),
      close),
    h("h3", { className: "graph-side-sub", textContent: "Its 10 nearest books" }),
    h("p", { className: "graph-side-stat", textContent: `${sameClass} of 10 share its LoC class · LoC itself would pick ${agree} of the same 10` }),
    h("ol", { className: "graph-nbs" }, list),
  ];
}

function renderSide() {
  const cur = current();
  const i = params().book;
  $("side").replaceChildren(...(i >= 0 ? renderBook(i, cur.variant) : renderOverview(cur.variant)));
}

// ---- leaderboard ----
function renderBars(cur) {
  const rows = state.index.variants.filter((v) => v.scores.p10_class != null)
    .sort((a, b) => b.scores.p10_class - a.scores.p10_class);
  if (state.index.random) rows.push({ model: "Random links", measure: "", scores: state.index.random, file: "" });
  $("bars").replaceChildren(...rows.map((v) => {
    const isRef = v.file === LCC_FILE;
    const fill = h("span", { className: "graph-bar-fill" });
    fill.style.width = `${v.scores.p10_class * 100}%`;
    const row = h(v.file && !isRef ? "button" : "div", { className: "graph-bar" + (isRef || !v.file ? " is-reference" : "") },
      h("span", { className: "graph-bar-name", textContent: (v.measure ? `${v.model} · ${v.measure}` : v.model)
        + (v.model.includes("learned from LCC") ? " (uses LoC labels)" : "") }),
      h("span", { className: "graph-bar-track" }, fill),
      h("span", { className: "graph-bar-value", textContent: `${Math.round(v.scores.p10_class * 100)}%` }));
    if (v === cur.variant) row.setAttribute("aria-current", "true");
    if (row.tagName === "BUTTON") {
      row.type = "button";
      row.addEventListener("click", () => {
        setParams({ model: v.model, measure: v.measure });
        $("stage").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    return h("li", {}, row);
  }));
}

// ---- render ----
async function render(animate = true) {
  const cur = current();
  const p = params();
  renderControls(cur);
  renderBars(cur);
  const [g, lcc] = await Promise.all([loadGraph(cur.variant.file), loadGraph(LCC_FILE)]);
  views.main.setData(p.arrange === "lcc" ? lcc.pos : g.pos, g.nb, animate);
  if (p.compare) views.lcc.setData(lcc.pos, lcc.nb, false);
  renderSide();
}

async function init() {
  try {
    state.index = await (await fetch(`${DATA}index.json`)).json();
  } catch {
    $("side").textContent = "Graph data isn't built yet. Run python graph/export.py.";
    return;
  }
  const counts = {};
  for (const b of state.index.books) for (const c of b.classes) counts[c] = (counts[c] || 0) + 1;
  Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach((c, i) => {
    state.colorVar[c] = i < N_COLORS ? `--class-${i + 1}` : "--class-other";
  });
  const style = getComputedStyle(document.documentElement);
  for (const [c, v] of Object.entries(state.colorVar)) state.colorOf[c] = style.getPropertyValue(v).trim();
  state.colorOf[""] = style.getPropertyValue("--class-other").trim();
  wireControls();
  await render(false);
  if (params().book >= 0) views.main.focusOn(params().book);
}

init();
