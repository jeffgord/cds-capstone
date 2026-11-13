"""API contract tests. Uses a FakeSearcher, so no model or index is needed: python -m pytest tests/"""
import pytest
from fastapi.testclient import TestClient

from api import books as B
from api.app import create_app
from api.searchers import ChunkHit

BOOKS = B.load_books()
IDS = sorted(BOOKS)


class FakeSearcher:
    """Returns several chunks per book (like Estee's summary + passage docs), best first."""

    def __init__(self, n_books=40):
        self.hits = []
        for i, gid in enumerate(IDS[:n_books]):
            score = 0.9 - i * 0.01
            self.hits.append(ChunkHit(gid, score, "summary", None, f"Title: x | Author: y | Summary: z"))
            self.hits.append(ChunkHit(gid, score - 0.005, "passage", 0, "Title: x | Subjects: y | Excerpt: some text"))

    def search(self, query, n):
        return self.hits[:n]

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
    assert {"rank", "gutenberg_id", "score", "matched_via", "passage_index", "snippet", "fields_matched", "book"} <= r.keys()
    assert {"title", "authors", "added_year", "description", "subjects", "topic_subjects", "locc", "url", "cover_url"} <= r["book"].keys()
    assert [x["rank"] for x in body["results"]] == [1, 2, 3, 4, 5]
    assert body["highlight_terms"] == ["bee", "honey"]


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
])
def test_display_name(raw, shown):
    assert B.display_name(raw) == shown


@pytest.mark.parametrize("code, label", [
    ("BV", "Practical Theology"), ("DS", "Asia"), ("D501", "History (General)"),
    ("E151", "History of the Americas"), ("JX", "International law"), ("KF", "Law of the United States"),
])
def test_lcc_label(code, label):
    assert B.lcc_label(code, B.load_lcc()) == label


def test_fields_matched_is_literal_overlap():
    rec = {"title": "Bees, Shown to the Children", "contributors": [], "subjects": [], "topic_subjects": ["Bees"], "description": ""}
    assert B.fields_matched(rec, "books about bees") == [{"field": "title", "terms": ["bees"]}, {"field": "subjects", "terms": ["bees"]}]
    assert B.fields_matched(rec, "honey") == []
