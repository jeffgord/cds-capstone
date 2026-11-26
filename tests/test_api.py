"""API contract tests. Uses a FakeSearcher, so no model or index is needed: python -m pytest tests/"""
import pytest
from fastapi.testclient import TestClient

from api import books as B
from api.app import create_app
from api.searchers import ChunkHit

BOOKS = B.load_books()
IDS = sorted(BOOKS)


class FakeSearcher:
    """Returns several chunks per book (like the index's summary + passage docs), best first."""

    def __init__(self, n_books=40):
        self.hits = []
        for i, gid in enumerate(IDS[:n_books]):
            score = 0.9 - i * 0.01
            self.hits.append(ChunkHit(gid, score, "summary", None, f"Title: x | Author: y | Summary: z"))
            self.hits.append(ChunkHit(gid, score - 0.005, "passage", 0, "Title: x | Subjects: y | Excerpt: some text"))

    def search(self, query, n):
        return self.hits[:n]

    def similarity(self, query, texts):
        # Longer texts score higher, so tests can tell which one should win.
        return [min(len(t) / 1000, 1.0) for t in texts]

    def info(self):
        return {"searcher": "fake", "model": "none", "n_vectors": len(self.hits), "score_kind": "cosine"}


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(searcher=FakeSearcher()))


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ready"] is True and body["n_books"] == len(BOOKS) and body["searcher"] == "fake"


def test_search_contract(client):
    body = client.get("/api/search", params={"q": "  bees  and honey ", "k": 5}).json()
    assert body["query"] == "bees and honey"
    assert body["has_more"] is True
    assert len(body["results"]) == 5
    r = body["results"][0]
    assert {"rank", "gutenberg_id", "score", "matched_via", "passage_index", "snippet", "book"} <= r.keys()
    assert {"title", "authors", "added_year", "description", "subjects", "topic_subjects", "locc", "url", "cover_url"} <= r["book"].keys()
    assert [x["rank"] for x in body["results"]] == [1, 2, 3, 4, 5]


def test_one_result_per_book_and_pages_dont_overlap(client):
    p1 = client.get("/api/search", params={"q": "x", "k": 10}).json()["results"]
    p2 = client.get("/api/search", params={"q": "x", "k": 10, "offset": 10}).json()["results"]
    ids = [r["gutenberg_id"] for r in p1 + p2]
    assert len(ids) == len(set(ids)) == 20
    assert p2[0]["rank"] == 11


def test_last_page_has_no_more(client):
    body = client.get("/api/search", params={"q": "x", "k": 10, "offset": 30}).json()
    assert len(body["results"]) == 10 and body["has_more"] is False


def test_k_is_clamped(client):
    big = TestClient(create_app(searcher=FakeSearcher(n_books=80)))
    assert len(big.get("/api/search", params={"q": "x", "k": 500}).json()["results"]) == 50


def test_bad_requests(client):
    assert client.get("/api/search", params={"q": "   "}).status_code == 400
    assert client.get("/api/search", params={"q": "x", "k": 0}).status_code == 422
    assert client.get("/api/books/999999999").status_code == 404


def test_no_index_is_503():
    app = create_app(load_in_background=False)
    c = TestClient(app)
    assert c.get("/api/health").json()["ready"] is False
    assert c.get("/api/search", params={"q": "x"}).status_code == 503


def test_snippet_never_shows_the_embedding_header(client):
    for r in client.get("/api/search", params={"q": "x", "k": 20}).json()["results"]:
        assert not (r["snippet"] or "").startswith("Title:")


def test_snippet_prefers_book_text():
    rec = {"description": "A summary.", "passages": ["First passage.", "Second."]}
    assert B.snippet(rec, "passage", 1, "Title: t | Excerpt: other") == "Second."
    assert B.snippet(rec, "summary", None, "Title: t | Summary: s") == "A summary."
    assert B.snippet(rec, None, None, "Title: t | Excerpt: chunk text") == "chunk text"
    assert B.snippet({"passages": []}, None, None, None) is None


def test_book_detail(client):
    gid = IDS[0]
    d = client.get(f"/api/books/{gid}").json()
    assert d["gutenberg_id"] == gid and "table_of_contents" in d and "has_text" in d


@pytest.mark.parametrize("raw, shown", [
    ("Sylvain, Adrien, 1826-1914", "Adrien Sylvain (1826-1914)"),
    ("Yonge, Charlotte M. (Charlotte Mary), 1823-1901", "Charlotte M. Yonge (1823-1901)"),
    ("Davy, Humphry, Sir, 1778-1829", "Sir Humphry Davy (1778-1829)"),
    ("Birkenhead, Frederick Edwin Smith, Earl of, 1872-1930", "Frederick Edwin Smith, Earl of Birkenhead (1872-1930)"),
    ("Bryce, James Bryce, Viscount, 1838-1922", "James Bryce, Viscount Bryce (1838-1922)"),
    ("Holbach, Paul Henri Thiry, baron d', 1723-1789", "Paul Henri Thiry, baron d'Holbach (1723-1789)"),
    ("Thomas, Aquinas, Saint, 1225?-1274", "Saint Thomas Aquinas (1225?-1274)"),
    ("Smith, Cecil Harcourt-, Sir, 1859-1944", "Sir Cecil Harcourt-Smith (1859-1944)"),
    ("Jones, William, F.S.A.", "William Jones, F.S.A."),
    ("Bull, Thomas, -1858", "Thomas Bull (died 1858)"),
    ("Black, Madeleine, 1873-", "Madeleine Black (born 1873)"),
    ("Intercollegiate Peace Association", "Intercollegiate Peace Association"),
    ("McCormick & Co. (Baltimore, Md.)", "McCormick & Co. (Baltimore, Md.)"),
    ("Brooklyn (New York, N.Y.). Committee of Ten", "Brooklyn (New York, N.Y.). Committee of Ten"),
])
def test_display_name(raw, shown):
    assert B.display_name(raw) == shown


LCC = B.load_lcc()


@pytest.mark.parametrize("code, trail", [
    ("BV", ["B", "BV"]), ("DS", ["D", "DS"]), ("T", ["T"]), ("d501", ["D", "D1-2027", "D501-680"]),
    ("QA76.73", ["Q", "QA1-939", "QA71-90", "QA75-76.95", "QA75.5-76.95"]),
])
def test_lcc_trail_walks_from_main_class_down(code, trail):
    assert [t["code"] for t in B.lcc_trail(code, LCC)] == trail


@pytest.mark.parametrize("code, label", [
    ("BV", "Practical Theology"), ("DS", "Asia"), ("KF", "Law of the United States"), ("J", "Political Science"),
    ("D501-680", "World War I (1914-1918)"), ("B*", "Philosophy (General)"),
])
def test_lcc_filter_label(code, label):
    assert B.lcc_filter_label(code, LCC) == label


@pytest.mark.parametrize("junk", ["*", "-", "Y", "123", "((", "Ω", ".", "Y12"])
def test_unknown_lcc_filter_has_no_label(junk):
    assert B.lcc_filter_label(junk, LCC) is None


@pytest.mark.parametrize("codes, flt, hit", [
    (["BX100"], "B", True), (["BX100"], "BX", True), (["BX100"], "BV", False),
    (["B105"], "B*", True), (["BX100"], "B*", False),
    (["D530"], "D501-680", True), (["D700"], "D501-680", False), (["DS10"], "D501-680", False),
    (["AC200"], "AC200", True), (["AC201"], "AC200", False),
    ([], "B", False), (["", None], "B", False), (["BX"], "", True),
])
def test_locc_matches(codes, flt, hit):
    assert B.locc_matches(codes, flt) is hit


@pytest.mark.parametrize("code", ["", " ", None, "123", "((", "Y12"])
def test_lcc_trail_never_crashes_on_odd_codes(code):
    assert isinstance(B.lcc_trail(code, LCC), list)


def test_why_scores_each_sentence(client):
    gid = next(g for g in IDS[:40] if BOOKS[g].get("passages") and BOOKS[g].get("description"))
    body = client.get(f"/api/books/{gid}/why", params={"q": "x", "matched_via": "passage", "passage_index": 0}).json()
    assert body["sentences"] and " ".join(x["text"] for x in body["sentences"]) == B.snippet(BOOKS[gid], "passage", 0, None)
    assert all(isinstance(x["score"], float) for x in body["sentences"])


def test_why_errors(client):
    assert client.get(f"/api/books/{IDS[0]}/why", params={"q": " "}).status_code == 400
    assert client.get("/api/books/999999999/why", params={"q": "x"}).status_code == 404

    class NoScorer:
        def search(self, query, n): return []
        def info(self): return {}
    c = TestClient(create_app(searcher=NoScorer()))
    assert c.get(f"/api/books/{IDS[0]}/why", params={"q": "x"}).status_code == 501


def test_sentences():
    long = "This sentence is long enough to stand alone."
    assert B.sentences(f"{long} {long}  {long}") == [long] * 3
    assert B.sentences(f"{long} (Dr. A. M. Hale, 1890.) {long}") == [long, "(Dr. A. M. Hale, 1890.)", long]
    assert B.sentences(f"{long} The problem...") == [long, "The problem..."]


def test_cors_only_when_configured(monkeypatch):
    origin = {"Origin": "https://ui.example.org"}
    plain = TestClient(create_app(searcher=FakeSearcher()))
    assert "access-control-allow-origin" not in plain.get("/api/health", headers=origin).headers
    monkeypatch.setenv("CORS_ORIGINS", "https://ui.example.org")
    split = TestClient(create_app(searcher=FakeSearcher()))
    assert split.get("/api/health", headers=origin).headers["access-control-allow-origin"] == "https://ui.example.org"


def test_cover_prefers_local_copy(tmp_path):
    rec = BOOKS[IDS[0]]
    assert B.card(rec, {}, covers_dir=tmp_path)["cover_url"].startswith("https://www.gutenberg.org/")
    (tmp_path / f"{IDS[0]}.jpg").write_bytes(b"jpg")
    assert B.card(rec, {}, covers_dir=tmp_path)["cover_url"] == f"/covers/{IDS[0]}.jpg"


def test_ui_files_are_revalidated(client):
    assert client.get("/app.js").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/health").headers


def test_search_within_a_bookshelf(client):
    shelf = next(s for gid in IDS[:40] for s in BOOKS[gid]["subjects"])
    body = client.get("/api/search", params={"q": "x", "shelf": shelf, "k": 50}).json()
    assert body["shelf"] == shelf and body["results"]
    assert all(shelf in r["book"]["subjects"] for r in body["results"])


def test_browse_a_bookshelf_without_a_query():
    c = TestClient(create_app(load_in_background=False))  # browsing needs no model
    shelf = next(s for gid in IDS for s in BOOKS[gid]["subjects"])
    body = c.get("/api/search", params={"shelf": shelf, "k": 5}).json()
    titles = [r["book"]["title"].lower() for r in body["results"]]
    assert titles == sorted(titles) and all(r["score"] is None for r in body["results"])
    assert body["total"] == sum(shelf in BOOKS[g]["subjects"] for g in IDS)


def test_filter_by_lcc_class_and_shelf():
    c = TestClient(create_app(load_in_background=False))
    body = c.get("/api/search", params={"lcc": "j", "k": 50}).json()
    assert body["lcc"] == "J" and body["total"] > 0
    assert all(any(cl["code"] == "J" for cl in r["book"]["classes"]) for r in body["results"])
    shelf = body["results"][0]["book"]["subjects"][0]
    both = c.get("/api/search", params={"lcc": "J", "shelf": shelf, "k": 50}).json()
    assert 0 < both["total"] <= body["total"] and all(shelf in r["book"]["subjects"] for r in both["results"])


def test_card_classes_use_main_class_names():
    rec = {"gutenberg_id": 1, "locc": ["JX", "JZ", "D501"]}
    assert [c["label"] for c in B.card(rec, LCC)["classes"]] == ["Political Science", "World History and History of Europe"]


def test_card_skips_empty_codes_and_duplicate_trails():
    card = B.card({"gutenberg_id": 1, "locc": ["BV", "", None, "BV"]}, LCC)
    assert [[t["code"] for t in trail] for trail in card["locc"]] == [["B", "BV"]]


def test_card_without_outline_falls_back_to_the_letter():
    assert B.card({"gutenberg_id": 1, "locc": ["JX"]}, {})["classes"] == [{"code": "J", "label": "J"}]


@pytest.mark.parametrize("junk", ["*", "((", "Ω", "D680-501", "[A-Z]", "X" * 500])
def test_junk_lcc_filter_is_an_empty_list_not_an_error(junk):
    c = TestClient(create_app(load_in_background=False))
    r = c.get("/api/search", params={"lcc": junk})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_filter_by_lcc_range():
    c = TestClient(create_app(load_in_background=False))
    body = c.get("/api/search", params={"lcc": "D501-680", "k": 50}).json()
    assert body["total"] > 0 and body["lcc_label"] == "World War I (1914-1918)"
    assert all(any(cl["code"] == "D" for cl in r["book"]["classes"]) for r in body["results"])

