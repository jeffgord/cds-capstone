// Drawing for the book graph page, on D3 (web/vendor/). Two parts:
// - GraphView: the big map, drawn on a canvas (1,000 dots stay fast), with d3-zoom for zoom, pan and
//   pinch, animated moves between layouts, class labels on clusters, and a labelled focus mode.
// - drawNeighborhood: a small force-directed SVG of one book and its 10 closest books.
// Neither knows about the page; graph.js feeds them positions, neighbor lists and colors.

const TAU = 2 * Math.PI;
const MORPH_MS = 900;
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

class GraphView {
  // opts: colorOf(i), classOf(i), titleOf(i), classLabel(code), matches(i) -> bool (search),
  //       onHover(i, event), onSelect(i), linkedState() -> {hover, selected, highlight}
  constructor(canvas, opts) {
    this.canvas = canvas;
    this.opts = opts;
    this.pos = null; // Float32Array [x0, y0, x1, y1, ...] in 0..1000
    this.nb = [];
    this.t = d3.zoomIdentity;
    this.zoom = d3.zoom().scaleExtent([0.6, 14]).on("zoom", (e) => {
      this.t = e.transform;
      this.draw();
    });
    d3.select(canvas).call(this.zoom);
    this.bindPointer();
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  setData(pos, nb, animate) {
    const next = Float32Array.from(pos.flat());
    this.nb = nb;
    this.timer?.stop();
    if (!this.pos || !animate || REDUCED_MOTION) {
      this.pos = next;
      this.draw();
      return;
    }
    const from = this.pos.slice();
    this.timer = d3.timer((elapsed) => {
      const e = d3.easeCubicInOut(Math.min(1, elapsed / MORPH_MS));
      for (let i = 0; i < next.length; i++) this.pos[i] = from[i] + (next[i] - from[i]) * e;
      this.draw();
      if (elapsed >= MORPH_MS) this.timer.stop();
    });
  }

  // ---- geometry ----
  size() {
    const ratio = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (this.canvas.width !== Math.round(w * ratio)) this.canvas.width = Math.round(w * ratio);
    if (this.canvas.height !== Math.round(h * ratio)) this.canvas.height = Math.round(h * ratio);
    return { w, h, ratio };
  }

  // Layouts are 0..1000 on both axes, stretched to fill the canvas; the top pad leaves room for the caption.
  base(i, w, h) {
    return [24 + (this.pos[2 * i] / 1000) * (w - 48), 64 + (this.pos[2 * i + 1] / 1000) * (h - 88)];
  }

  toScreen(i, w, h) {
    return this.t.apply(this.base(i, w, h));
  }

  nearest(px, py) {
    if (!this.pos) return -1;
    const { w, h } = this.size();
    let best = -1;
    let bestD = 100; // within 10px
    for (let i = 0; i < this.pos.length / 2; i++) {
      const [x, y] = this.toScreen(i, w, h);
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bestD) [best, bestD] = [i, d];
    }
    return best;
  }

  zoomBy(factor) {
    d3.select(this.canvas).transition().duration(250).call(this.zoom.scaleBy, factor);
  }

  reset() {
    d3.select(this.canvas).transition().duration(500).call(this.zoom.transform, d3.zoomIdentity);
  }

  // Flies to one book, zoomed in enough to read its neighborhood.
  focusOn(i) {
    if (!this.pos) return;
    const { w, h } = this.size();
    const [x, y] = this.base(i, w, h);
    const k = Math.max(this.t.k, 2.5);
    const target = d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-x, -y);
    d3.select(this.canvas).transition().duration(REDUCED_MOTION ? 0 : 750).call(this.zoom.transform, target);
  }

  // Hover and click; d3-zoom already handles drag, wheel and pinch, and swallows the click after a drag.
  bindPointer() {
    const c = this.canvas;
    const at = (e) => {
      const r = c.getBoundingClientRect();
      return this.nearest(e.clientX - r.left, e.clientY - r.top);
    };
    c.addEventListener("pointermove", (e) => {
      const i = at(e);
      c.style.cursor = i >= 0 ? "pointer" : "grab";
      this.opts.onHover(i, e);
    });
    c.addEventListener("pointerleave", (e) => this.opts.onHover(-1, e));
    c.addEventListener("click", (e) => this.opts.onSelect(at(e)));
  }

  // ---- drawing ----
  draw() {
    if (!this.pos || !this.canvas.clientWidth) return;
    const { w, h, ratio } = this.size();
    const ctx = this.canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const n = this.pos.length / 2;
    const pts = Array.from({ length: n }, (_, i) => this.toScreen(i, w, h));
    const { hover, selected, highlight } = this.opts.linkedState();
    const focus = selected >= 0 ? selected : hover;
    const near = new Set(focus >= 0 ? [focus, ...this.nb[focus]] : []);
    const lit = (i) => (!highlight || this.opts.classOf(i) === highlight) && this.opts.matches(i);
    const dimmed = (i) => (selected >= 0 ? !near.has(i) : !lit(i));

    // Faint links to each book's 3 closest, so clusters read as connected without a hairball.
    ctx.lineWidth = 0.6;
    ctx.strokeStyle = css("--graph-edge");
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      if (dimmed(i)) continue;
      for (const j of this.nb[i].slice(0, 3)) {
        ctx.moveTo(...pts[i]);
        ctx.lineTo(...pts[j]);
      }
    }
    ctx.stroke();

    const r = Math.min(5, 2.4 * Math.sqrt(this.t.k));
    for (let i = 0; i < n; i++) {
      ctx.globalAlpha = dimmed(i) ? 0.12 : 0.92;
      ctx.fillStyle = this.opts.colorOf(i);
      ctx.beginPath();
      ctx.arc(...pts[i], r, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    if (focus >= 0) this.drawFocus(ctx, pts, focus, r);
    else this.drawClassLabels(ctx, pts, highlight);
    if (selected >= 0 && hover >= 0 && hover !== selected) { // a book hovered in the side panel's list
      ctx.strokeStyle = css("--ink");
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(...pts[hover], r + 6, 0, TAU);
      ctx.stroke();
    }
  }

  // Names each class where its books cluster most densely, and only if at least 8 of them sit within a
  // small radius there. A class scattered over the map gets no label rather than a misleading one.
  drawClassLabels(ctx, pts, highlight) {
    const groups = {};
    pts.forEach((p, i) => {
      const c = this.opts.classOf(i);
      if (c) (groups[c] ||= []).push(p);
    });
    const { w, h } = this.size();
    const radius = Math.min(w, h) * 0.07;
    const placed = [];
    ctx.font = "700 12px 'Open Sans', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const [c, ps] of Object.entries(groups).sort((a, b) => b[1].length - a[1].length)) {
      if (ps.length < 8 || (highlight && c !== highlight)) continue;
      let best = [];
      for (const p of ps) {
        const near = ps.filter((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < radius);
        if (near.length > best.length) best = near;
      }
      if (best.length < 8) continue;
      const text = this.opts.classLabel(c);
      const half = ctx.measureText(text).width / 2 + 4;
      const mx = best.reduce((s, p) => s + p[0], 0) / best.length;
      const cy = best.reduce((s, p) => s + p[1], 0) / best.length - 14; // just above the cluster
      if (mx < 0 || mx > w || cy < 0 || cy > h) continue;
      const cx = Math.min(Math.max(mx, half), w - half); // keep the whole label on the canvas
      const box = [cx - half, cy - 9, 2 * half, 18];
      if (placed.some((b) => overlaps(b, box))) continue;
      placed.push(box);
      label(ctx, text, cx, cy, css("--ink"), css("--page"));
    }
  }

  // A book and its 10 closest: links, rings and titles that don't overlap or run off the canvas.
  drawFocus(ctx, pts, focus, r) {
    const halo = css("--page");
    ctx.strokeStyle = css("--accent");
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (const j of this.nb[focus]) {
      ctx.moveTo(...pts[focus]);
      ctx.lineTo(...pts[j]);
    }
    ctx.stroke();
    for (const j of [...this.nb[focus], focus]) {
      ctx.fillStyle = this.opts.colorOf(j);
      ctx.strokeStyle = j === focus ? css("--ink") : halo;
      ctx.lineWidth = j === focus ? 2.5 : 1.5;
      ctx.beginPath();
      ctx.arc(...pts[j], j === focus ? r + 4 : r + 1.5, 0, TAU);
      ctx.fill();
      ctx.stroke();
    }
    const { w, h } = this.size();
    const placed = [];
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const j of [focus, ...this.nb[focus]]) {
      ctx.font = j === focus ? "700 13px 'Open Sans', sans-serif" : "12px 'Open Sans', sans-serif";
      const text = shorten(this.opts.titleOf(j), j === focus ? 60 : 38);
      const [x, y] = pts[j];
      const tw = ctx.measureText(text).width;
      const spots = [[x + r + 6, y], [x - r - 6 - tw, y], [x - tw / 2, y - 14], [x - tw / 2, y + 14]];
      for (const [lx, ly] of spots) {
        const box = [lx - 2, ly - 8, tw + 4, 16];
        if (box[0] < 0 || box[0] + box[2] > w || box[1] < 0 || box[1] + box[3] > h) continue;
        if (placed.some((b) => overlaps(b, box))) continue;
        placed.push(box);
        label(ctx, text, lx, ly, css(j === focus ? "--ink" : "--ink-2"), halo);
        break;
      }
    }
  }
}

// One book in the middle, its 10 closest books around it as numbered dots (matching the list under it),
// and a link between two neighbors when one is also among the other's 10 closest. The layout is solved
// up front (300 ticks), so it appears settled instead of wobbling in.
function drawNeighborhood(svgEl, center, nb, nbOf, opts) {
  const width = svgEl.clientWidth || 300;
  const height = 230;
  const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`);
  svg.selectAll("*").remove();
  const ids = [center, ...nb];
  const nodes = ids.map((id, k) => ({ id, k }));
  const inSet = new Set(ids);
  const links = nb.map((id) => ({ source: center, target: id, main: true }));
  for (const a of nb) {
    for (const b of nbOf(a)) if (b !== center && inSet.has(b) && a < b) links.push({ source: a, target: b });
  }
  d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id)
      .distance((l) => (l.main ? 90 : 60)).strength((l) => (l.main ? 0.6 : 0.1)))
    .force("charge", d3.forceManyBody().strength(-320))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide(20))
    .stop()
    .tick(300);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  nodes.forEach((d) => {
    d.x = clamp(d.x, 14, width - 14);
    d.y = clamp(d.y, 14, height - 14);
  });

  svg.append("g").selectAll("line").data(links).join("line")
    .attr("class", (l) => (l.main ? "nbhd-link is-main" : "nbhd-link"))
    .attr("x1", (l) => l.source.x).attr("y1", (l) => l.source.y)
    .attr("x2", (l) => l.target.x).attr("y2", (l) => l.target.y);
  const node = svg.append("g").selectAll("g").data(nodes).join("g")
    .attr("class", (d) => (d.k === 0 ? "nbhd-node is-center" : "nbhd-node"))
    .attr("transform", (d) => `translate(${d.x},${d.y})`)
    .attr("tabindex", (d) => (d.k === 0 ? null : 0))
    .attr("role", (d) => (d.k === 0 ? null : "button"))
    .attr("aria-label", (d) => opts.titleOf(d.id))
    .on("click", (_, d) => d.k && opts.onSelect(d.id))
    .on("keydown", (e, d) => {
      if (d.k && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        opts.onSelect(d.id);
      }
    })
    .on("pointerenter focus", (_, d) => opts.onHover(d.id))
    .on("pointerleave blur", () => opts.onHover(-1));
  node.append("title").text((d) => opts.titleOf(d.id));
  node.append("circle").attr("r", (d) => (d.k === 0 ? 13 : 10)).style("fill", (d) => opts.colorOf(d.id));
  node.append("text").attr("dy", "0.35em").text((d) => (d.k === 0 ? "" : d.k));
}

function label(ctx, text, x, y, color, halo) {
  ctx.lineWidth = 4;
  ctx.lineJoin = "round";
  ctx.strokeStyle = halo;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

function overlaps(a, b) {
  return a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3];
}

function shorten(text, max) {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

window.GraphView = GraphView;
window.drawNeighborhood = drawNeighborhood;
