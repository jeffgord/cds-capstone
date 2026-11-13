// Gutenberg Semantic Search UI. Talks only to /api (contract in api/README.md).
// The URL (?q=&book=) is the one source of truth for what's on screen: every action writes it,
// render() reads it, so back/forward and shared links always show the same thing.
"use strict";

const PAGE_SIZE = 10;
const RECENT_KEY = "gss.recent";
const RECENT_MAX = 6;
// Checked against Estee's BGE-base index on 2026-11-12 (docs/decisions.md): each returns an on-topic top 3.
// Recheck whenever the index changes.
const EXAMPLES = [
  "peaceful diplomacy without military conflict",
  "daily life of pioneer settlers on the American frontier",
  "home remedies and herbal medicine",
  "women fighting for the right to vote",
];
const ROLE_PHRASE = {
  Editor: "edited by", Translator: "translated by", Illustrator: "illustrated by",
  Compiler: "compiled by", "Author of introduction, etc.": "introduction by",
};

const $ = (id) => document.getElementById(id);
const els = {
  form: $("search-form"), q: $("q"), recent: $("recent"), guide: $("guide"), examples: $("examples"),
  status: $("status"), section: $("results-section"), title: $("results-title"), results: $("results"),
  more: $("more"), panel: $("panel"), panelEmpty: $("panel-empty"), panelBody: $("panel-body"),
};

const state = { query: "", results: [], hasMore: false, terms: [], health: null, searchToken: 0, bookToken: 0 };

// ---------- small DOM helpers (text goes in via textContent only; data is never parsed as HTML) ----------
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) el.append(c);
  return el;
}

function svgChevron() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 10 10");
  svg.setAttribute("class", "chev");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", "M1 3l4 4 4-4");
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", "1.6");
  svg.append(p);
  return svg;
}

// Wrap query-word matches in <mark> without ever touching innerHTML.
function highlighted(text, terms) {
  const frag = document.createDocumentFragment();
  if (!text) return frag;
  const usable = terms.filter((t) => t.length > 2).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!usable.length) { frag.append(text); return frag; }
  const re = new RegExp(`\\b(${usable.join("|")})\\w*`, "gi");
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) frag.append(text.slice(last, m.index));
    frag.append(h("mark", {}, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) frag.append(text.slice(last));
  return frag;
}

function cover(book, id) {
  const box = h("div", { class: "cover", "aria-hidden": "true" });
  const fallback = () => { box.textContent = (book.title || "?").trim().charAt(0).toUpperCase(); };
  if (!book.cover_url) { fallback(); return box; }
  const img = h("img", { src: book.cover_url, alt: "", loading: "lazy", decoding: "async", width: 56, height: 84 });
  img.addEventListener("error", () => { img.remove(); fallback(); }, { once: true });
  box.append(img);
  return box;
}

function authorLine(authors, max = 3) {
  if (!authors.length) return "Unknown author";
  const main = authors.filter((a) => a.role === "Author").map((a) => a.display);
  const others = authors.filter((a) => a.role !== "Author")
    .map((a) => (ROLE_PHRASE[a.role] ? `${ROLE_PHRASE[a.role]} ${a.display}` : `${a.display} (${a.role.toLowerCase()})`));
  const parts = [main.join(", "), ...others].filter(Boolean);
  const shown = parts.slice(0, max).join("; ");
  return parts.length > max ? `${shown}; and ${parts.length - max} more` : shown;
}

function lccText(locc) {
  return locc.map((l) => `${l.label} (${l.code})`).join(", ");
}

// ---------- URL state ----------
function readUrl() {
  const p = new URLSearchParams(location.search);
  const book = Number.parseInt(p.get("book") || "", 10);
  return { q: (p.get("q") || "").trim(), book: Number.isFinite(book) ? book : null };
}

function writeUrl({ q, book }, push = true) {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (book) p.set("book", String(book));
  const url = `${location.pathname}${p.toString() ? `?${p}` : ""}`;
  if (url === `${location.pathname}${location.search}`) return;
  history[push ? "pushState" : "replaceState"](null, "", url);
}

// ---------- recent searches (per-browser convenience; storage may be unavailable) ----------
function loadRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").filter((x) => typeof x === "string"); }
  catch { return []; }
}
function saveRecent(q) {
  const list = [q, ...loadRecent().filter((x) => x.toLowerCase() !== q.toLowerCase())].slice(0, RECENT_MAX);
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* private mode: skip */ }
}
function clearRecent() {
  try { localStorage.removeItem(RECENT_KEY); } catch { /* ignore */ }
}

let recentIndex = -1;
function showRecent() {
  const typed = els.q.value.trim().toLowerCase();
  const items = loadRecent().filter((x) => !typed || (x.toLowerCase().includes(typed) && x.toLowerCase() !== typed));
  els.recent.replaceChildren();
  recentIndex = -1;
  if (!items.length) { hideRecent(); return; }
  els.recent.append(h("li", { class: "recent-label", role: "presentation" }, "Recent searches"));
  items.forEach((text, i) => {
    els.recent.append(h("li", {
      role: "option", id: `recent-${i}`, "aria-selected": "false",
      onmousedown: (e) => { e.preventDefault(); pickRecent(text); },
    }, text));
  });
  els.recent.append(h("li", { role: "presentation", class: "recent-label" },
    h("button", { type: "button", class: "text-button", onmousedown: (e) => { e.preventDefault(); clearRecent(); hideRecent(); } }, "Clear recent searches")));
  els.recent.hidden = false;
  els.q.setAttribute("aria-expanded", "true");
}
function hideRecent() {
  els.recent.hidden = true;
  els.q.setAttribute("aria-expanded", "false");
  els.q.removeAttribute("aria-activedescendant");
  recentIndex = -1;
}
function moveRecent(step) {
  const options = [...els.recent.querySelectorAll('[role="option"]')];
  if (!options.length) return;
  recentIndex = (recentIndex + step + options.length) % options.length;
  options.forEach((o, i) => o.setAttribute("aria-selected", String(i === recentIndex)));
  els.q.setAttribute("aria-activedescendant", options[recentIndex].id);
}
function pickRecent(text) {
  els.q.value = text;
  hideRecent();
  submit(text);
}

// ---------- API ----------
async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(body.detail || res.statusText); err.status = res.status; throw err; }
  return body;
}

function setStatus(node) {
  els.status.replaceChildren(...(node ? [node] : []));
}

function statusBox(...children) { return h("div", { class: "status-box" }, ...children); }

const API_DOWN = () => statusBox(
  h("strong", {}, "The search API isn't running. "),
  "Start it from the repo root with ", h("code", {}, "uvicorn api.app:app"), " and reload this page.",
);

async function checkHealth() {
  try {
    state.health = await api("/api/health");
  } catch {
    state.health = null;
    setStatus(API_DOWN());
    return false;
  }
  if (state.health.ready) {
    $("tagline").textContent = `Search ${state.health.n_books.toLocaleString()} nonfiction books by what they're about`;
    return true;
  }
  if (state.health.loading) {
    setStatus(statusBox("Loading the search model. This takes a few seconds the first time."));
    setTimeout(() => { checkHealth().then((ok) => ok && render()); }, 1500);
    return false;
  }
  setStatus(statusBox(h("strong", {}, "Search isn't available. "), state.health.error || "No search index is loaded."));
  return false;
}

// ---------- results ----------
function matchedIn(r) {
  if (r.matched_via === "summary") return "Matched in the catalog summary";
  if (r.matched_via === "passage" && r.passage_index !== null) {
    return `Matched in passage ${r.passage_index + 1} of ${r.n_passages || "?"} from the book`;
  }
  if (r.matched_via === "passage") return "Matched in a passage from the book";
  return "Matched in the book's indexed text";
}

function whyBox(r, id) {
  const shared = r.fields_matched.length
    ? h("p", {}, "Your words also appear in: ",
        r.fields_matched.map((f) => `${f.field} (${f.terms.join(", ")})`).join("; "))
    : h("p", {}, "No shared words: this matched on meaning.");
  return h("div", { class: "why", id, hidden: true },
    h("p", { class: "why-source" }, matchedIn(r)),
    r.snippet ? h("blockquote", {}, highlighted(r.snippet, state.terms)) : null,
    shared,
    h("p", { class: "why-note" },
      "The score is the cosine similarity between your query and this text. Higher is closer. Compare scores only within one search."),
  );
}

function resultItem(r) {
  const b = r.book;
  const whyId = `why-${r.gutenberg_id}`;
  const summaryId = `summary-${r.gutenberg_id}`;
  const subjects = b.topic_subjects.length ? b.topic_subjects : b.subjects;
  const meta = [b.added_year ? `Added to Gutenberg ${b.added_year}` : null, b.locc.length ? lccText(b.locc) : null].filter(Boolean);

  const summary = b.description
    ? h("p", { class: "summary clamped", id: summaryId, title: b.description }, b.description)
    : h("p", { class: "summary summary-missing" }, "No summary in the catalog.");

  const why = whyBox(r, whyId);
  const whyButton = h("button", {
    type: "button", class: "why-button", "aria-expanded": "false", "aria-controls": whyId,
    onclick: () => {
      const open = whyButton.getAttribute("aria-expanded") !== "true";
      whyButton.setAttribute("aria-expanded", String(open));
      why.hidden = !open;
    },
  }, h("span", { class: "score" }, r.score.toFixed(3)), h("span", {}, "Why this book"), svgChevron());

  const actions = h("div", { class: "actions" }, whyButton);
  if (b.description && b.description.length > 180) {
    const more = h("button", {
      type: "button", class: "text-button", "aria-controls": summaryId, "aria-expanded": "false",
      onclick: () => {
        const el = $(summaryId);
        const open = el.classList.toggle("clamped") === false;
        more.textContent = open ? "Less" : "More";
        more.setAttribute("aria-expanded", String(open));
      },
    }, "More");
    actions.append(more);
  }
  actions.append(h("a", { class: "read-link", href: b.url, target: "_blank", rel: "noopener" }, "Read on Gutenberg"));

  return h("li", { class: "result", "data-id": r.gutenberg_id },
    cover(b, r.gutenberg_id),
    h("div", { class: "result-body" },
      h("h3", { class: "result-title" },
        h("a", {
          href: `?${new URLSearchParams({ q: state.query, book: r.gutenberg_id })}`,
          onclick: (e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); openBook(r.gutenberg_id); },
        }, b.title)),
      h("p", { class: "authors" }, authorLine(b.authors)),
      meta.length ? h("p", { class: "meta" }, meta.map((m) => h("span", {}, m))) : null,
      summary,
      subjects.length ? h("ul", { class: "tags", "aria-label": "Subjects" },
        subjects.slice(0, 4).map((s) => h("li", { class: "tag" }, s)),
        subjects.length > 4 ? h("li", { class: "tag" }, `+${subjects.length - 4}`) : null) : null,
      actions,
      why,
    ),
  );
}

function renderResults() {
  els.section.hidden = false;
  els.title.replaceChildren("Results", h("span", { class: "count" },
    state.results.length ? `${state.results.length}${state.hasMore ? "+" : ""} books for "${state.query}"` : ""));
  els.results.replaceChildren(...state.results.map(resultItem));
  els.more.hidden = !state.hasMore;
  markOpen();
}

async function runSearch(q) {
  const token = ++state.searchToken;
  state.query = q;
  els.q.value = q;
  els.guide.hidden = true;
  els.results.setAttribute("aria-busy", "true");
  setStatus(document.createTextNode("Searching..."));
  try {
    const data = await api(`/api/search?${new URLSearchParams({ q, k: PAGE_SIZE, offset: 0 })}`);
    if (token !== state.searchToken) return;
    state.results = data.results;
    state.hasMore = data.has_more;
    state.terms = data.highlight_terms || [];
    setStatus(data.results.length
      ? h("span", { class: "visually-hidden" }, `${data.results.length} results`)
      : statusBox("No books matched. Try describing the topic another way."));
    renderResults();
  } catch (err) {
    if (token !== state.searchToken) return;
    if (err.status === 503) await checkHealth();
    else if (!err.status) setStatus(API_DOWN());
    else setStatus(statusBox(h("strong", {}, "Search failed. "), err.message));
  } finally {
    if (token === state.searchToken) els.results.removeAttribute("aria-busy");
  }
}

async function showMore() {
  els.more.disabled = true;
  els.more.textContent = "Loading...";
  try {
    const data = await api(`/api/search?${new URLSearchParams({ q: state.query, k: PAGE_SIZE, offset: state.results.length })}`);
    const seen = new Set(state.results.map((r) => r.gutenberg_id));
    const fresh = data.results.filter((r) => !seen.has(r.gutenberg_id));
    state.results.push(...fresh);
    state.hasMore = data.has_more;
    els.results.append(...fresh.map(resultItem));
    els.title.querySelector(".count").textContent = `${state.results.length}${state.hasMore ? "+" : ""} books for "${state.query}"`;
    els.more.hidden = !state.hasMore;
    setStatus(h("span", { class: "visually-hidden" }, `${fresh.length} more results`));
    markOpen();
  } catch {
    setStatus(API_DOWN());
  } finally {
    els.more.disabled = false;
    els.more.textContent = "Show more";
  }
}

function showHome() {
  state.searchToken++;
  state.query = "";
  state.results = [];
  els.q.value = "";
  els.guide.hidden = false;
  els.section.hidden = true;
  els.results.replaceChildren();
  if (state.health && state.health.ready) setStatus(null);
}

// ---------- detail panel ----------
function isNarrow() { return window.matchMedia("(max-width: 1023px)").matches; }

function markOpen() {
  const id = readUrl().book;
  for (const li of els.results.children) li.classList.toggle("is-open", Number(li.dataset.id) === id);
}

function factRow(label, value) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) return null;
  const cell = Array.isArray(value) ? h("ul", {}, value.map((v) => h("li", {}, v))) : value;
  return h("tr", {}, h("th", { scope: "row" }, label), h("td", {}, cell));
}

function renderBook(d) {
  const toc = d.table_of_contents || [];
  const tocList = h("ol", { class: "toc" }, toc.slice(0, 25).map((t) => h("li", {}, t)));
  const tocMore = toc.length > 25 ? h("button", {
    type: "button", class: "text-button",
    onclick: (e) => { tocList.replaceChildren(...toc.map((t) => h("li", {}, t))); e.currentTarget.remove(); },
  }, `Show all ${toc.length} entries`) : null;

  const intro = d.introduction || "";
  const introShort = intro.length > 1200 ? `${intro.slice(0, 1200).replace(/\s+\S*$/, "")}...` : intro;
  const introP = h("p", {}, introShort);
  const introMore = intro.length > 1200 ? h("button", {
    type: "button", class: "text-button",
    onclick: (e) => { introP.textContent = intro; e.currentTarget.remove(); },
  }, "Show the whole excerpt") : null;

  els.panelBody.replaceChildren(
    h("div", { class: "panel-top" },
      cover(d, d.gutenberg_id),
      h("div", {},
        h("h2", { class: "panel-title", id: "panel-title" }, d.title),
        d.subtitle ? h("p", { class: "panel-subtitle" }, d.subtitle) : null),
      h("button", { type: "button", class: "close-button", "aria-label": "Close details", onclick: closeBook }, "×")),
    h("table", { class: "facts" }, h("tbody", {},
      factRow("Authors", d.authors.map((a) => (a.role === "Author" ? a.display : `${a.display}, ${a.role.toLowerCase()}`))),
      factRow("Subjects", d.topic_subjects),
      factRow("Bookshelves", d.subjects),
      factRow("Classification", d.locc.map((l) => `${l.label} (${l.code})`)),
      factRow("Added to Gutenberg", d.added_year ? String(d.added_year) : null),
      factRow("Gutenberg ID", h("a", { href: d.url, target: "_blank", rel: "noopener" }, `#${d.gutenberg_id}, read or download`)),
    )),
    h("h3", {}, "Summary", h("span", { class: "label-note" }, "auto-generated by Project Gutenberg")),
    h("p", {}, d.description || "No summary in the catalog."),
    toc.length ? [h("h3", {}, "Contents"), tocList, tocMore] : null,
    intro ? [h("h3", {}, "From the introduction"), introP, introMore] : null,
    !d.has_text ? h("p", {}, "No text was extracted from this book, only its catalog record.") : null,
  );
  els.panelEmpty.hidden = true;
  els.panelBody.hidden = false;
}

async function showBook(id) {
  const token = ++state.bookToken;
  els.panel.classList.add("is-open");
  document.body.classList.toggle("sheet-open", isNarrow());
  els.panel.setAttribute("aria-labelledby", "panel-title");
  els.panelEmpty.hidden = true;
  els.panelBody.hidden = false;
  els.panelBody.replaceChildren(h("p", {}, "Loading..."));
  try {
    const d = await api(`/api/books/${id}`);
    if (token !== state.bookToken) return;
    renderBook(d);
    els.panel.scrollTop = 0;
    if (isNarrow()) els.panel.focus();
  } catch (err) {
    if (token !== state.bookToken) return;
    els.panelBody.replaceChildren(
      h("div", { class: "panel-top" }, h("p", {}, err.status === 404 ? "That book isn't in the dataset." : "Couldn't load this book."),
        h("button", { type: "button", class: "close-button", "aria-label": "Close details", onclick: closeBook }, "×")));
  }
  markOpen();
}

function hideBook() {
  state.bookToken++;
  els.panel.classList.remove("is-open");
  document.body.classList.remove("sheet-open");
  els.panel.removeAttribute("aria-labelledby");
  els.panelBody.hidden = true;
  els.panelEmpty.hidden = false;
  markOpen();
}

function openBook(id) {
  writeUrl({ q: state.query, book: id });
  render();
}

function closeBook() {
  const { q, book } = readUrl();
  writeUrl({ q, book: null });
  render();
  // Return focus to the title that opened the panel, so keyboard users don't lose their place.
  const link = els.results.querySelector(`[data-id="${CSS.escape(String(book))}"] .result-title a`);
  if (link) link.focus();
}

// ---------- render from URL ----------
let lastBook = null;
async function render() {
  const { q, book } = readUrl();
  if (!q) showHome();
  else if (q !== state.query || !state.results.length) {
    if (state.health && state.health.ready) await runSearch(q);
    else { els.q.value = q; els.guide.hidden = true; }
  }
  if (book && book !== lastBook) showBook(book);
  else if (!book && lastBook) hideBook();
  lastBook = book;
}

function submit(q) {
  q = q.trim().replace(/\s+/g, " ");
  if (!q) { els.q.focus(); return; }
  saveRecent(q);
  hideRecent();
  writeUrl({ q, book: null });
  state.query = ""; // force a fresh search even when the query is unchanged
  render();
}

// ---------- wiring ----------
els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const options = [...els.recent.querySelectorAll('[role="option"]')];
  if (!els.recent.hidden && recentIndex >= 0 && options[recentIndex]) { pickRecent(options[recentIndex].textContent); return; }
  submit(els.q.value);
});
els.q.addEventListener("focus", showRecent);
els.q.addEventListener("input", showRecent);
els.q.addEventListener("blur", () => setTimeout(hideRecent, 100));
els.q.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { if (els.recent.hidden) showRecent(); moveRecent(1); e.preventDefault(); }
  else if (e.key === "ArrowUp" && !els.recent.hidden) { moveRecent(-1); e.preventDefault(); }
  else if (e.key === "Escape" && !els.recent.hidden) { hideRecent(); e.stopPropagation(); }
});
els.more.addEventListener("click", showMore);
document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); els.q.focus(); els.q.select(); }
  else if (e.key === "Escape" && readUrl().book) closeBook();
});
window.addEventListener("popstate", render);

for (const ex of EXAMPLES) {
  els.examples.append(h("button", { type: "button", class: "example", onclick: () => submit(ex) }, ex));
}

checkHealth().then(() => render());
