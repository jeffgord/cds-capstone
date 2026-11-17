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
    def search(q: str = "", k: int = Query(10, ge=1), offset: int = Query(0, ge=0)):
        query = " ".join(q.split())
        if not query:
            raise HTTPException(400, "Empty query")
        if slot.searcher is None:
            raise HTTPException(503, slot.error or "The search model is still loading")
        k = min(k, MAX_K)
        want = offset + k + 1  # one extra book tells us whether there's a next page
        started = time.perf_counter()

        ranked = best_per_book(slot.searcher, query, want, keep=lambda gid: gid in books)
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
            "k": k,
            "offset": offset,
            "took_ms": round((time.perf_counter() - started) * 1000),
            "has_more": len(ranked) > offset + k,
            "score_kind": slot.searcher.info().get("score_kind"),
            "results": results,
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

    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
