// Book graph page. Loads the precomputed variants from graph-data/ (built by graph/export.py) and drives
// the drawing in graph-draw.js. The URL (?model=&measure=&arrange=lcc&compare=1&book=) is the single
// source of truth for what's on screen.

const DATA = "graph-data/";
const LCC_FILE = "lcc-itself-reference";
const N_COLORS = 12; // the 12 biggest classes get a color token each, the rest share --class-other

// Display names and a short note on where each method comes from and how it works. Keys are the model and
// measure names in index.json.
const MODELS = {
  "bge-base": ["BGE base (search)", "Trained on large sets of query and passage pairs, so a search lands next to the passages that answer it."],
  "mpnet": ["MPNet", "From Sentence Transformers, built on Microsoft's MPNet. Tuned on about 1 billion sentence pairs to spot sentences that mean the same thing."],
  "TF-IDF word overlap": ["Word overlap (no model)", "Books are close if they share the same rare words."],
  "LCC": ["Library classes (the target)", "Books are close if their call numbers share more levels, like D, then DS, then a number range."],
};
const MEASURES = {
  "Cosine": "Two books are close if their vectors point the same way.",
  "Shared neighbors": "Two books are close if the same books surround them.",
};

const $ = (id) => document.getElementById(id);
const state = { index: null, graphs: {}, hover: -1, highlight: "", query: "", colorOf: {}, colorVar: {} };

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
// Short names for map labels: "Philosophy. Psychology. Religion" -> "Philosophy".
const shortName = (c) => className(c).split(". ")[0].split(" and ")[0];
const modelName = (m) => MODELS[m]?.[0] || m;
// "MPNet, shared neighbors"; acronyms like CSLS keep their capitals
const lowerFirst = (s) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
const variantName = (v) => (v.file === LCC_FILE || !MEASURES[v.measure] ? modelName(v.model) : `${modelName(v.model)}, ${lowerFirst(v.measure)}`);
const explain = (v) => [MODELS[v.model]?.[1], MEASURES[v.measure]].filter(Boolean).join(" ");

function matches(i) {
  if (!state.query) return true;
  const b = book(i);
  return b.title.toLowerCase().includes(state.query) || (b.author || "").toLowerCase().includes(state.query);
}

// ---- views ----
const viewOpts = {
  colorOf: (i) => state.colorOf[classOf(i)] || state.colorOf[""],
  classOf,
  titleOf: (i) => book(i).title,
  classLabel: shortName,
  matches,
  linkedState: () => ({ hover: state.hover, selected: params().book, highlight: state.highlight }),
  onHover(i, e) {
    if (i !== state.hover) {
      state.hover = i;
      drawAll();
    }
    showBookTip(i, e);
  },
  onSelect(i) {
    select(i === params().book ? -1 : i);
  },
};
const views = { main: new GraphView($("canvas-main"), viewOpts), lcc: new GraphView($("canvas-lcc"), viewOpts) };

function drawAll() {
  views.main.draw();
  if (params().compare) views.lcc.draw();
}

function select(i, { fly = false } = {}) {
  setParams({ book: i }, { animate: false });
  if (fly && i >= 0) views.main.focusOn(i);
}

// ---- floating tip (books on the map, rows of the leaderboard) ----
function tip() {
  return $("tip") || document.body.appendChild(h("div", { id: "tip", className: "graph-tip", hidden: true }));
}

function placeTip(el, x, y) {
  el.hidden = false;
  el.style.left = `${Math.min(x + 14, document.documentElement.clientWidth - el.offsetWidth - 8)}px`;
  el.style.top = `${y + 14}px`;
}

function showBookTip(i, e) {
  const el = tip();
  if (i < 0 || params().book >= 0 || !e) {
    el.hidden = true;
    return;
  }
  el.replaceChildren(h("strong", { textContent: book(i).title }),
    h("span", { textContent: book(i).author || "" }),
    h("span", { textContent: book(i).classes.map((c) => `${className(c)} (${c})`).join(", ") || "No class" }));
  placeTip(el, e.pageX, e.pageY);
}

// ---- controls ----
function renderControls(cur) {
  const p = params();
  $("model").replaceChildren(...cur.models.map((m) =>
    h("option", { value: m, textContent: modelName(m), selected: m === cur.model })));
  $("measure").replaceChildren(...cur.options.map((v) =>
    h("option", { value: v.measure, textContent: v.measure, selected: v === cur.variant })));
  $("measure").disabled = cur.options.length < 2;
  $("model-tip").replaceChildren(h("strong", { textContent: modelName(cur.model) }), h("span", { textContent: MODELS[cur.model]?.[1] || "" }));
  $("measure-tip").replaceChildren(h("strong", { textContent: cur.variant.measure }), h("span", { textContent: MEASURES[cur.variant.measure] || "" }));
  $("arrange-model").setAttribute("aria-pressed", String(p.arrange !== "lcc"));
  $("arrange-lcc").setAttribute("aria-pressed", String(p.arrange === "lcc"));
  $("compare").setAttribute("aria-pressed", String(p.compare));
  $("compare").classList.toggle("is-active", p.compare);
  $("view-lcc").hidden = !p.compare;
  $("stage").classList.toggle("is-split", p.compare);
  $("kicker-main").textContent = p.arrange === "lcc" ? "Grouped by library class, links from" : "Grouped by";
  $("caption-main").textContent = variantName(cur.variant);
}

function wireControls() {
  $("model").addEventListener("change", (e) => setParams({ model: e.target.value, measure: "" }));
  $("measure").addEventListener("change", (e) => setParams({ measure: e.target.value }));
  $("arrange-model").addEventListener("click", () => setParams({ arrange: "" }));
  $("arrange-lcc").addEventListener("click", () => setParams({ arrange: "lcc" }));
  $("compare").addEventListener("click", () => setParams({ compare: !params().compare }, { animate: false }));
  $("find").addEventListener("input", (e) => {
    state.query = e.target.value.trim().toLowerCase();
    const n = state.query ? state.index.books.filter((_, i) => matches(i)).length : 0;
    $("find-count").textContent = state.query ? (n ? `${n} match${n === 1 ? "" : "es"}` : "No match") : "";
    if (params().book >= 0) select(-1); // a selected book would hide the matches
    else drawAll();
  });
  $("controls").addEventListener("submit", (e) => {
    e.preventDefault();
    const i = state.index.books.findIndex((_, j) => state.query && matches(j));
    if (i >= 0) select(i, { fly: true });
  });
  document.querySelectorAll("[data-zoom]").forEach((btn) => btn.addEventListener("click", () => {
    const z = btn.dataset.zoom;
    if (z === "reset") views.main.reset();
    else views.main.zoomBy(z === "in" ? 1.5 : 1 / 1.5);
  }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && params().book >= 0) select(-1);
  });
}

// ---- side panel ----
function dot(c) {
  const el = h("span", { className: "graph-dot" });
  el.style.background = `var(${state.colorVar[c] || "--class-other"})`;
  return el;
}

function meter(value, text) {
  const fill = h("span", { className: "graph-meter-fill" });
  fill.style.width = `${value * 100}%`;
  return h("li", {}, h("span", { className: "graph-meter-value", textContent: `${Math.round(value * 100)}%` }),
    h("span", { className: "graph-meter-text", textContent: ` ${text}` }), h("span", { className: "graph-meter" }, fill));
}

function renderOverview(variant) {
  const counts = {};
  for (const b of state.index.books) for (const c of b.classes) counts[c] = (counts[c] || 0) + 1;
  const order = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  return [
    h("h2", { className: "graph-side-head", textContent: "Match with library classes" }),
    h("ul", { className: "graph-meters" },
      variant.scores.p10_class != null ? meter(variant.scores.p10_class, "of a book's 10 closest books share its class") : null,
      variant.scores.p10_sub != null ? meter(variant.scores.p10_sub, "share its subclass") : null),
    h("h2", { className: "graph-side-head", textContent: "Library classes" }),
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
  const img = h("img", { src: b.cover, alt: "", loading: "lazy" });
  img.addEventListener("error", () => img.replaceWith(h("span", { className: "graph-cover-fallback", textContent: b.title[0] })));
  const close = h("button", { type: "button", className: "graph-close", ariaLabel: "Close", textContent: "×" });
  close.addEventListener("click", () => select(-1));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "graph-nbhd");
  svg.setAttribute("aria-label", `${b.title} and its 10 closest books`);
  const list = nb.map((j, k) => {
    const btn = h("button", { type: "button", className: "graph-nb" },
      h("span", { className: "graph-nb-num", textContent: k + 1 }), dot(classOf(j)),
      h("span", { className: "graph-nb-title", textContent: book(j).title }),
      shared(j) ? h("span", { className: "graph-nb-same", textContent: "same class" }) : null);
    btn.addEventListener("click", () => select(j, { fly: true }));
    btn.addEventListener("pointerenter", () => { state.hover = j; drawAll(); });
    btn.addEventListener("pointerleave", () => { state.hover = -1; drawAll(); });
    return h("li", {}, btn);
  });
  requestAnimationFrame(() => drawNeighborhood(svg, i, nb, (j) => state.graphs[variant.file].nb[j].slice(0, 10), {
    colorOf: viewOpts.colorOf,
    titleOf: (j) => book(j).title,
    onSelect: (j) => select(j, { fly: true }),
    onHover: (j) => {
      document.querySelectorAll(".graph-nb").forEach((el, k) => el.classList.toggle("is-hover", nb[k] === j));
    },
  }));
  return [
    h("div", { className: "graph-book" }, h("div", { className: "graph-cover" }, img),
      h("div", {}, h("h2", { className: "graph-book-title", textContent: b.title }),
        h("p", { className: "graph-book-author", textContent: b.author || "" }),
        h("p", { className: "graph-book-classes" }, b.classes.map((c) => h("span", { className: "chip chip-class" }, dot(c), ` ${className(c)} (${c})`))),
        h("a", { className: "graph-open", href: `./?book=${b.id}`, textContent: "Open in search →" })),
      close),
    h("h3", { className: "graph-side-sub", textContent: "10 closest books" }),
    h("p", { className: "graph-side-stat",
      textContent: `${nb.filter(shared).length} of 10 share its class. The library classes would pick ${nb.filter((j) => lccNb.has(j)).length} of the same 10.` }),
    svg,
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
  if (state.index.random) rows.push({ model: "Random", measure: "", scores: state.index.random, file: "" });
  $("bars").replaceChildren(...rows.map((v) => {
    const isRef = v.file === LCC_FILE || !v.file;
    const name = v.file ? variantName(v) : "Random links (the floor)";
    const fill = h("span", { className: "graph-bar-fill" });
    fill.style.width = `${v.scores.p10_class * 100}%`;
    const row = h(isRef ? "div" : "button", { className: "graph-bar" + (isRef ? " is-reference" : "") },
      h("span", { className: "graph-bar-name", textContent: name }),
      h("span", { className: "graph-bar-track" }, fill),
      h("span", { className: "graph-bar-value", textContent: `${Math.round(v.scores.p10_class * 100)}%` }));
    const why = v.file ? explain(v) : "Each book linked to 10 books picked at random.";
    row.addEventListener("pointerenter", (e) => {
      tip().replaceChildren(h("strong", { textContent: name }), h("span", { textContent: why }));
      placeTip(tip(), e.pageX, e.pageY);
    });
    row.addEventListener("pointerleave", () => { tip().hidden = true; });
    if (v === cur.variant) row.setAttribute("aria-current", "true");
    if (!isRef) {
      row.type = "button";
      row.setAttribute("aria-description", why);
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
  const style = getComputedStyle(document.documentElement);
  Object.keys(counts).sort((a, b) => counts[b] - counts[a]).forEach((c, i) => {
    state.colorVar[c] = i < N_COLORS ? `--class-${i + 1}` : "--class-other";
    state.colorOf[c] = style.getPropertyValue(state.colorVar[c]).trim();
  });
  state.colorOf[""] = style.getPropertyValue("--class-other").trim();
  wireControls();
  await render(false);
  if (params().book >= 0) views.main.focusOn(params().book);
}

init();
