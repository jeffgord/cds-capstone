"""Search API + UI server. Run from the repo root:  uvicorn api.app:app --reload
The contract lives in api/README.md; the UI in web/ only talks to the /api routes."""
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import books as B
from api.searchers import Searcher, best_per_book, load_searcher

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_K = 50


class SearcherSlot:
    """Holds the searcher while it loads in the background, so the server (and the UI's "loading" state)
    is up in a second instead of waiting on the model."""

    def __init__(self):
        self.searcher: Searcher | None = None
        self.error: str | None = None
        self.loading = False

    def load(self, loader=load_searcher):
        self.loading = True
        try:
            self.searcher = loader()
        except Exception as e:  # shown in /api/health and the UI, so the cause is visible
            self.error = str(e)
        finally:
            self.loading = False


def create_app(searcher: Searcher | None = None, books_dir: Path = B.BOOKS_DIR, load_in_background: bool = True) -> FastAPI:
    app = FastAPI(title="Gutenberg Semantic Search API")
    # Locally the API serves web/ itself (same origin). When the UI is hosted elsewhere, e.g. Cloudflare
    # Pages, list its origin here: CORS_ORIGINS=https://our-site.pages.dev
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["Accept"])
    books = B.load_books(books_dir)
    outline = B.load_lcc()
    slot = SearcherSlot()
    if searcher is not None:
        slot.searcher = searcher
    elif load_in_background:
        slot.loading = True
        threading.Thread(target=slot.load, daemon=True).start()
    else:
        slot.error = "No searcher configured"
    app.state.slot = slot

    @app.middleware("http")
    async def revalidate_ui_files(request, call_next):
        """Make browsers check for a new index.html, app.js and style.css on every load (a cheap 304
        when unchanged). Without this they guess a cache lifetime and can mix old and new files."""
        response = await call_next(request)
        if not request.url.path.startswith(("/api/", "/covers/")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    def health():
        info = slot.searcher.info() if slot.searcher else {}
        return {
            "ready": slot.searcher is not None,
            "loading": slot.loading,
            "error": slot.error,
            "n_books": len(books),
            **info,
        }

    @app.get("/api/search")
    def search(q: str = "", shelf: str = "", k: int = Query(10, ge=1), offset: int = Query(0, ge=0)):
        """Semantic search, optionally only among books on one Gutenberg bookshelf. With a shelf and
        no query, it lists that shelf's books by title (no scores), for browsing."""
        query = " ".join(q.split())
        shelf = shelf.strip()
        if not query and not shelf:
            raise HTTPException(400, "Empty query")
        k = min(k, MAX_K)
        started = time.perf_counter()
        on_shelf = lambda gid: gid in books and (not shelf or shelf in (books[gid].get("subjects") or []))
        if not query:
            return browse_shelf(shelf, on_shelf, k, offset, started)
        if slot.searcher is None:
            raise HTTPException(503, slot.error or "The search model is still loading")
        want = offset + k + 1  # one extra book tells us whether there's a next page

        ranked = best_per_book(slot.searcher, query, want, keep=on_shelf)
        page = ranked[offset:offset + k]

        results = []
        for i, hit in enumerate(page):
            record = books[hit.gutenberg_id]
            results.append({
                "rank": offset + i + 1,
                "gutenberg_id": hit.gutenberg_id,
                "score": round(hit.score, 4),
                "matched_via": hit.doc_type,
                "passage_index": hit.passage_index,
                "n_passages": len(record.get("passages") or []),
                "snippet": B.snippet(record, hit.doc_type, hit.passage_index, hit.text),
                "book": B.card(record, outline),
            })
        return {
            "query": query,
            "shelf": shelf or None,
            "k": k,
            "offset": offset,
            "took_ms": round((time.perf_counter() - started) * 1000),
            "has_more": len(ranked) > offset + k,
            "score_kind": slot.searcher.info().get("score_kind"),
            "results": results,
        }

    def browse_shelf(shelf: str, on_shelf, k: int, offset: int, started: float) -> dict:
        """All books on one bookshelf, by title. There's no query, so there are no scores."""
        ids = sorted((gid for gid in books if on_shelf(gid)), key=lambda gid: (books[gid].get("title") or "").lower())
        page = ids[offset:offset + k]
        return {
            "query": "",
            "shelf": shelf,
            "k": k,
            "offset": offset,
            "took_ms": round((time.perf_counter() - started) * 1000),
            "has_more": len(ids) > offset + k,
            "total": len(ids),
            "score_kind": None,
            "results": [{
                "rank": offset + i + 1, "gutenberg_id": gid, "score": None, "matched_via": None,
                "passage_index": None, "n_passages": len(books[gid].get("passages") or []), "snippet": None,
                "book": B.card(books[gid], outline),
            } for i, gid in enumerate(page)],
        }

    @app.get("/api/books/{gutenberg_id}")
    def book(gutenberg_id: int):
        record = books.get(gutenberg_id)
        if record is None:
            raise HTTPException(404, "No such book")
        return B.detail(record, outline)

    @app.get("/api/books/{gutenberg_id}/why")
    def why(gutenberg_id: int, q: str = "", matched_via: str | None = None, passage_index: int | None = None):
        """Semantic evidence for one result: the search model scores each sentence of the matched text
        against the query, so the UI can highlight the closest one."""
        query = " ".join(q.split())
        record = books.get(gutenberg_id)
        if not query:
            raise HTTPException(400, "Empty query")
        if record is None:
            raise HTTPException(404, "No such book")
        if slot.searcher is None:
            raise HTTPException(503, slot.error or "The search model is still loading")
        if not hasattr(slot.searcher, "similarity"):
            raise HTTPException(501, "This search backend can't score text")
        started = time.perf_counter()
        quote = B.snippet(record, matched_via, passage_index, None)
        sents = B.sentences(quote) if quote else []
        scores = slot.searcher.similarity(query, sents) if sents else []
        return {
            "gutenberg_id": gutenberg_id,
            "query": query,
            "took_ms": round((time.perf_counter() - started) * 1000),
            "sentences": [{"text": t, "score": round(sc, 4)} for t, sc in zip(sents, scores)],
        }

    if B.COVERS_DIR.exists():
        app.mount("/covers", StaticFiles(directory=B.COVERS_DIR), name="covers")
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
