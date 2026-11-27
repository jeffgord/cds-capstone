// Canvas renderer for the book graph page: zoom and pan, animated moves between layouts, class labels
// on clusters, and a focus mode that labels a book and its neighbours. Knows nothing about the page;
// graph.js feeds it positions, neighbour lists and colours.

const TAU = 2 * Math.PI;
const MORPH_MS = 900;
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

class GraphView {
  // opts: colorOf(i) -> css colour, classOf(i) -> class code, titleOf(i), classLabel(code),
  //       onHover(i, event), onSelect(i), linkedState() -> {hover, selected, highlight}
  constructor(canvas, opts) {
    this.canvas = canvas;
    this.opts = opts;
    this.pos = null;      // current positions, Float32Array [x0, y0, x1, y1, ...] in 0..1000
    this.target = null;
    this.nb = [];
    this.view = { k: 1, x: 0, y: 0 }; // zoom and pan, on top of the fit-to-canvas transform
    this.frame = 0;
    this.bindEvents();
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  setData(pos, nb, animate) {
    const next = Float32Array.from(pos.flat());
    this.nb = nb;
    if (!this.pos || !animate || REDUCED_MOTION) {
      this.pos = next;
      this.draw();
      return;
    }
    const from = this.pos.slice();
    const start = performance.now();
    cancelAnimationFrame(this.frame);
    const step = (now) => {
      const t = Math.min(1, (now - start) / MORPH_MS);
      const e = ease(t);
      for (let i = 0; i < next.length; i++) this.pos[i] = from[i] + (next[i] - from[i]) * e;
      this.draw();
      if (t < 1) this.frame = requestAnimationFrame(step);
    };
    this.frame = requestAnimationFrame(step);
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

  // Layouts are 0..1000 on both axes; they're stretched to fill the canvas (a mild distortion that
  // beats leaving the sides of a wide canvas empty). The top pad leaves room for the caption.
  toScreen(i, w, h) {
    const x = 24 + (this.pos[2 * i] / 1000) * (w - 48);
    const y = 64 + (this.pos[2 * i + 1] / 1000) * (h - 88);
    return [(x - w / 2) * this.view.k + w / 2 + this.view.x, (y - h / 2) * this.view.k + h / 2 + this.view.y];
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

  zoomBy(factor, cx, cy) {
    const { w, h } = this.size();
    cx ??= w / 2;
    cy ??= h / 2;
    const k = Math.max(0.6, Math.min(12, this.view.k * factor));
    const f = k / this.view.k;
    this.view.x = cx - w / 2 - (cx - w / 2 - this.view.x) * f;
    this.view.y = cy - h / 2 - (cy - h / 2 - this.view.y) * f;
    this.view.k = k;
    this.draw();
  }

  reset() {
    this.view = { k: 1, x: 0, y: 0 };
    this.draw();
  }

  // Centres the view on one book, zoomed in enough to read its neighbourhood.
  focusOn(i) {
    const { w, h } = this.size();
    const target = Math.max(this.view.k, 2.5);
    this.view.k = target;
    this.view.x = 0;
    this.view.y = 0;
    const [x, y] = this.toScreen(i, w, h);
    this.view.x = w / 2 - x;
    this.view.y = h / 2 - y;
    this.draw();
  }

  // ---- events ----
  bindEvents() {
    const c = this.canvas;
    let drag = null;
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      this.zoomBy(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    c.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, y: e.clientY, vx: this.view.x, vy: this.view.y, moved: false };
      c.setPointerCapture(e.pointerId);
    });
    c.addEventListener("pointermove", (e) => {
      const r = c.getBoundingClientRect();
      if (drag) {
        const dx = e.clientX - drag.x;
        const dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
        if (drag.moved) {
          this.view.x = drag.vx + dx;
          this.view.y = drag.vy + dy;
          this.draw();
          return;
        }
      }
      const i = this.nearest(e.clientX - r.left, e.clientY - r.top);
      c.style.cursor = drag?.moved ? "grabbing" : i >= 0 ? "pointer" : "grab";
      this.opts.onHover(i, e);
    });
    c.addEventListener("pointerup", (e) => {
      const r = c.getBoundingClientRect();
      if (drag && !drag.moved) this.opts.onSelect(this.nearest(e.clientX - r.left, e.clientY - r.top));
      drag = null;
    });
    c.addEventListener("pointerleave", (e) => this.opts.onHover(-1, e));
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
    const inClass = (i) => !highlight || this.opts.classOf(i) === highlight;
    const dimmed = (i) => (focus >= 0 && selected >= 0 ? !near.has(i) : !inClass(i));

    // Faint links to each book's 3 nearest, so islands read as connected without a hairball.
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

    const r = Math.min(5, 2.4 * Math.sqrt(this.view.k));
    const halo = css("--page");
    for (let i = 0; i < n; i++) {
      ctx.globalAlpha = dimmed(i) ? 0.12 : 0.92;
      ctx.fillStyle = this.opts.colorOf(i);
      ctx.beginPath();
      ctx.arc(...pts[i], r, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    if (focus < 0) this.drawClassLabels(ctx, pts, highlight);
    else this.drawFocus(ctx, pts, focus, r, halo);
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
      const cy = best.reduce((s, p) => s + p[1], 0) / best.length - 14; // just above the island
      if (mx < 0 || mx > w || cy < 0 || cy > h) continue;
      const cx = Math.min(Math.max(mx, half), w - half); // keep the whole label on the canvas
      const box = [cx - ctx.measureText(text).width / 2 - 4, cy - 9, ctx.measureText(text).width + 8, 18];
      if (placed.some((b) => overlaps(b, box))) continue;
      placed.push(box);
      label(ctx, text, cx, cy, css("--ink"), css("--page"));
    }
  }

  // A book and its 10 neighbours: links, rings and readable titles that don't overlap.
  drawFocus(ctx, pts, focus, r, halo) {
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
    const placed = [];
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    for (const j of [focus, ...this.nb[focus]]) {
      ctx.font = j === focus ? "700 13px 'Open Sans', sans-serif" : "12px 'Open Sans', sans-serif";
      const text = shorten(this.opts.titleOf(j), j === focus ? 60 : 38);
      const [x, y] = pts[j];
      const wText = ctx.measureText(text).width;
      // Try right, then left, then above and below the dot.
      const spots = [[x + r + 6, y], [x - r - 6 - wText, y], [x - wText / 2, y - 14], [x - wText / 2, y + 14]];
      const { w: cw, h: ch } = this.size();
      for (const [lx, ly] of spots) {
        const box = [lx - 2, ly - 8, wText + 4, 16];
        if (box[0] < 0 || box[0] + box[2] > cw || box[1] < 0 || box[1] + box[3] > ch) continue;
        if (placed.some((b) => overlaps(b, box))) continue;
        placed.push(box);
        label(ctx, text, lx, ly, css(j === focus ? "--ink" : "--ink-2"), halo);
        break;
      }
    }
  }
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
