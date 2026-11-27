// Book graph page: draws the precomputed graph variants from graph-data/ (built by graph/export.py).
// The URL (?model=&measure=&compare=1) is the single source of truth for what's on screen.

const DATA = "graph-data/";
const LCC_FILE = "lcc-itself-reference";
const N_COLORS = 12; // the 12 biggest classes get a colour token each, the rest share --class-other
const SCORES = [
  ["p10_class", "Neighbours in the same LoC class"],
  ["p10_sub", "Neighbours in the same LoC subclass"],
  ["nmi", "Graph communities match LoC classes (NMI)"],
  ["vote_f1", "Class guessed from neighbours (macro-F1)"],
];

const $ = (id) => document.getElementById(id);
const state = { index: null, graphs: {}, hover: -1, highlight: "", colorOf: {} };
const views = { main: { canvas: $("canvas-main"), file: "" }, lcc: { canvas: $("canvas-lcc"), file: LCC_FILE } };

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  Object.assign(el, props);
  el.append(...kids.flat().filter((k) => k != null));
  return el;
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function params() {
  const p = new URLSearchParams(location.search);
  return { model: p.get("model") || "", measure: p.get("measure") || "", compare: p.get("compare") === "1" };
}

function setParams(next) {
  const p = { ...params(), ...next };
  const q = new URLSearchParams();
  if (p.model) q.set("model", p.model);
  if (p.measure) q.set("measure", p.measure);
  if (p.compare) q.set("compare", "1");
  history.replaceState(null, "", `${location.pathname}?${q}`);
  render();
}

async function loadGraph(file) {
  if (!state.graphs[file]) {
    const g = await (await fetch(`${DATA}${file}.json`)).json();
    g.nbrs = state.index.books.map(() => []);
    for (let i = 0; i < g.edges.length; i += 2) {
      g.nbrs[g.edges[i]].push(g.edges[i + 1]);
      g.nbrs[g.edges[i + 1]].push(g.edges[i]);
    }
    state.graphs[file] = g;
  }
  return state.graphs[file];
}

function variantsFor(model) {
  return state.index.variants.filter((v) => v.model === model && v.file !== LCC_FILE);
}

function current() {
  const { model, measure } = params();
  const models = [...new Set(state.index.variants.filter((v) => v.file !== LCC_FILE).map((v) => v.model))];
  const m = models.includes(model) ? model : models[0];
  const options = variantsFor(m);
  return { models, model: m, options, variant: options.find((v) => v.measure === measure) || options[0] };
}

function renderControls(cur) {
  $("model").replaceChildren(...cur.models.map((m) => h("option", { value: m, textContent: m, selected: m === cur.model })));
  $("measure").replaceChildren(...cur.options.map((v) =>
    h("option", { value: v.measure, textContent: v.measure, selected: v === cur.variant })));
  $("measure").disabled = cur.options.length < 2;
  const compare = params().compare;
  $("compare").setAttribute("aria-pressed", String(compare));
  $("compare").classList.toggle("is-active", compare);
  $("view-lcc").hidden = !compare;
  $("views").classList.toggle("is-split", compare);
}

function rank(key, value) {
  const all = state.index.variants.filter((v) => v.file !== LCC_FILE && v.scores[key] != null);
  return 1 + all.filter((v) => v.scores[key] > value).length + "/" + all.length;
}

function renderScores(variant) {
  const ref = state.index.variants.find((v) => v.file === LCC_FILE)?.scores || {};
  $("scores").replaceChildren(...SCORES.filter(([k]) => variant.scores[k] != null).map(([k, label]) =>
    h("div", { className: "graph-score" },
      h("span", { className: "graph-score-value", textContent: variant.scores[k].toFixed(2) }),
      h("span", { className: "graph-score-label", textContent: label }),
      h("span", { className: "graph-score-meta",
        textContent: `rank ${rank(k, variant.scores[k])}` + (ref[k] != null ? ` · LoC itself ${ref[k].toFixed(2)}` : "") }))));
}

function renderLegend() {
  const counts = {};
  for (const b of state.index.books) for (const c of b.classes) counts[c] = (counts[c] || 0) + 1;
  const order = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  order.forEach((c, i) => { state.colorOf[c] = i < N_COLORS ? `--class-${i + 1}` : "--class-other"; });
  $("legend").replaceChildren(...order.map((c) => {
    const btn = h("button", { type: "button", className: "graph-legend-item", ariaPressed: String(state.highlight === c) },
      h("span", { className: "graph-swatch" }),
      `${state.index.classes[c] || c} (${c}) · ${counts[c]}`);
    btn.querySelector(".graph-swatch").style.background = `var(${state.colorOf[c]})`;
    btn.addEventListener("click", () => {
      state.highlight = state.highlight === c ? "" : c;
      renderLegend();
      draw();
    });
    return h("li", {}, btn);
  }));
}

function nodeColor(i) {
  const c = state.index.books[i].classes[0];
  return c ? css(state.colorOf[c]) : css("--class-other");
}

function fit(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const hgt = Math.min(w, 640);
  canvas.style.height = `${hgt}px`;
  canvas.width = w * ratio;
  canvas.height = hgt * ratio;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, w, h: hgt };
}

function project(g, i, w, hgt) {
  const pad = 12;
  return [pad + (g.pos[i][0] / 1000) * (w - 2 * pad), pad + (g.pos[i][1] / 1000) * (hgt - 2 * pad)];
}

function drawView(view) {
  const g = state.graphs[view.file];
  if (!g || view.canvas.closest("[hidden]")) return;
  const { ctx, w, h: hgt } = fit(view.canvas);
  view.size = [w, hgt];
  const pts = g.pos.map((_, i) => project(g, i, w, hgt));
  const focus = state.hover;
  const inClass = (i) => !state.highlight || state.index.books[i].classes.includes(state.highlight);

  ctx.lineWidth = 0.5;
  ctx.strokeStyle = css("--graph-edge");
  ctx.beginPath();
  for (let k = 0; k < g.edges.length; k += 2) {
    const [a, b] = [g.edges[k], g.edges[k + 1]];
    if (state.highlight && !(inClass(a) && inClass(b))) continue;
    ctx.moveTo(...pts[a]);
    ctx.lineTo(...pts[b]);
  }
  ctx.stroke();

  for (let i = 0; i < pts.length; i++) {
    ctx.globalAlpha = inClass(i) ? 1 : 0.12;
    ctx.fillStyle = nodeColor(i);
    ctx.beginPath();
    ctx.arc(...pts[i], 2.6, 0, 2 * Math.PI);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  if (focus >= 0) {
    ctx.strokeStyle = css("--ink");
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    for (const j of g.nbrs[focus]) {
      ctx.moveTo(...pts[focus]);
      ctx.lineTo(...pts[j]);
    }
    ctx.stroke();
    for (const j of [focus, ...g.nbrs[focus]]) {
      ctx.fillStyle = nodeColor(j);
      ctx.strokeStyle = css("--ink");
      ctx.beginPath();
      ctx.arc(...pts[j], j === focus ? 6 : 4, 0, 2 * Math.PI);
      ctx.fill();
      ctx.stroke();
    }
  }
}

function draw() {
  drawView(views.main);
  drawView(views.lcc);
}

function nearest(view, ev) {
  const g = state.graphs[view.file];
  if (!g || !view.size) return -1;
  const rect = view.canvas.getBoundingClientRect();
  const [x, y] = [ev.clientX - rect.left, ev.clientY - rect.top];
  let best = -1, bestD = 64; // within 8px
  g.pos.forEach((_, i) => {
    const [px, py] = project(g, i, ...view.size);
    const d = (px - x) ** 2 + (py - y) ** 2;
    if (d < bestD) [best, bestD] = [i, d];
  });
  return best;
}

function showTip(i, ev) {
  const tip = $("tip");
  if (i < 0) { tip.hidden = true; return; }
  const b = state.index.books[i];
  const n = state.graphs[views.main.file]?.nbrs[i] || [];
  const same = n.filter((j) => state.index.books[j].classes.some((c) => b.classes.includes(c))).length;
  tip.replaceChildren(
    h("strong", { textContent: b.title }),
    h("span", { textContent: b.classes.map((c) => `${state.index.classes[c] || c} (${c})`).join(", ") || "No LoC class" }),
    h("span", { textContent: `${same} of ${n.length} neighbours share its class` }));
  tip.hidden = false;
  tip.style.left = `${Math.min(ev.pageX + 14, document.documentElement.clientWidth - tip.offsetWidth - 8)}px`;
  tip.style.top = `${ev.pageY + 14}px`;
}

function wire(view) {
  view.canvas.addEventListener("mousemove", (ev) => {
    const i = nearest(view, ev);
    if (i !== state.hover) { state.hover = i; draw(); }
    showTip(i, ev);
    view.canvas.style.cursor = i >= 0 ? "pointer" : "default";
  });
  view.canvas.addEventListener("mouseleave", () => { state.hover = -1; showTip(-1); draw(); });
  view.canvas.addEventListener("click", (ev) => {
    const i = nearest(view, ev);
    if (i >= 0) location.href = `./?book=${state.index.books[i].id}`;
  });
}

async function render() {
  const cur = current();
  renderControls(cur);
  renderScores(cur.variant);
  views.main.file = cur.variant.file;
  $("caption-main").textContent = `${cur.variant.model} · ${cur.variant.measure}`;
  await Promise.all([loadGraph(views.main.file), params().compare ? loadGraph(LCC_FILE) : null]);
  draw();
}

async function init() {
  try {
    state.index = await (await fetch(`${DATA}index.json`)).json();
  } catch {
    $("scores").textContent = "Graph data isn't built yet. Run python graph/export.py.";
    return;
  }
  renderLegend();
  $("model").addEventListener("change", (e) => setParams({ model: e.target.value, measure: "" }));
  $("measure").addEventListener("change", (e) => setParams({ measure: e.target.value }));
  $("compare").addEventListener("click", () => setParams({ compare: !params().compare }));
  wire(views.main);
  wire(views.lcc);
  window.addEventListener("resize", draw);
  render();
}

init();
