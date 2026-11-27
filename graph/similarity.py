"""Ways to score how similar two books are, and ways to turn those scores into a graph.

Every similarity function returns a dense n x n matrix (n = 1,000 books, so this is small). The
diagonal is meaningless and the graph builders ignore it.
"""
import numpy as np
from scipy import sparse


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.linalg.norm(x, axis=1, keepdims=True).clip(1e-12)


def cosine(x: np.ndarray) -> np.ndarray:
    """Plain cosine on unit vectors."""
    return x @ x.T


def whitened_cosine(x: np.ndarray, dims: int = 16) -> np.ndarray:
    """Cosine after centering and PCA whitening. Sentence embeddings all lean the same way
    (anisotropy), which squeezes cosines into a narrow band; whitening spreads them out. Only 16
    dimensions: with 1,000 books, whitening more of them mostly amplifies noise (p10_class .54 at 16, .40
    at 256 on mpnet)."""
    c = x - x.mean(0)
    u, s, vt = np.linalg.svd(c, full_matrices=False)
    w = normalize((c @ vt[:dims].T) / s[:dims])
    return w @ w.T


def csls(sim: np.ndarray, k: int = 10) -> np.ndarray:
    """Cross-domain similarity local scaling: subtracts each book's average similarity to its k nearest
    books, so "hub" books that are close to everything stop being everyone's neighbour."""
    s = sim.copy()
    np.fill_diagonal(s, -np.inf)
    r = np.sort(s, axis=1)[:, -k:].mean(1)
    return 2 * sim - r[:, None] - r[None, :]


def shared_neighbours(sim: np.ndarray, k: int = 20) -> np.ndarray:
    """Jaccard overlap of two books' k-nearest-neighbour lists (plus a tiny bit of the raw score to
    break ties). Two books are close if the same books surround them."""
    nb = _top_k(sim, k)
    b = np.zeros_like(sim, dtype=np.float32)
    np.put_along_axis(b, nb, 1.0, axis=1)
    inter = b @ b.T
    return inter / (2 * k - inter) + 1e-3 * sim


def chunk_maxsim(chunks: np.ndarray, owner: np.ndarray, n: int) -> np.ndarray:
    """Compares books chunk by chunk instead of averaging first: for each chunk of book A, its best
    match among book B's chunks, averaged over A's chunks, then made symmetric."""
    starts = np.flatnonzero(np.r_[True, owner[1:] != owner[:-1]])  # chunks are grouped by book
    s = chunks @ chunks.T
    best = np.maximum.reduceat(s, starts, axis=1)               # chunk x book
    a = np.add.reduceat(best, starts, axis=0) / np.diff(np.r_[starts, len(owner)])[:, None]
    return (a + a.T) / 2


def tfidf_cosine(texts: list[str], owner: np.ndarray, n: int) -> np.ndarray:
    """Word-overlap baseline (not used for search): TF-IDF over each book's text. Shows how much the
    embedding models add over shared vocabulary."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    docs = [""] * n
    for t, i in zip(texts, owner):
        docs[i] += " " + t
    m = TfidfVectorizer(sublinear_tf=True, stop_words="english", min_df=2).fit_transform(docs)
    return (m @ m.T).toarray()


def lcc_similarity(trails: list[list[list[str]]], seed: int = 0) -> np.ndarray:
    """The reference: how many levels of the LCC hierarchy two books share (main class, subclass,
    number ranges). A tiny random jitter breaks ties so equal books don't all link the same way."""
    nodes = {}
    rows, cols = [], []
    for i, book in enumerate(trails):
        for code in {c for trail in book for c in trail}:
            rows.append(i)
            cols.append(nodes.setdefault(code, len(nodes)))
    b = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(trails), len(nodes)))
    jitter = np.random.default_rng(seed).random((len(trails), len(trails))) * 1e-3
    return (b @ b.T).toarray() + (jitter + jitter.T) / 2


def _top_k(sim: np.ndarray, k: int) -> np.ndarray:
    s = sim.copy()
    np.fill_diagonal(s, -np.inf)
    return np.argpartition(-s, k, axis=1)[:, :k]


def knn_graph(sim: np.ndarray, k: int = 10, mutual: bool = False) -> sparse.csr_matrix:
    """Each book links to its k most similar books. Union by default (an edge if either book picked
    the other); mutual keeps only pairs that picked each other, which is stricter and leaves some
    books with no links."""
    nb = _top_k(sim, k)
    rows = np.repeat(np.arange(len(sim)), k)
    a = sparse.csr_matrix((np.ones(rows.size), (rows, nb.ravel())), shape=sim.shape)
    a = a.minimum(a.T) if mutual else a.maximum(a.T)
    return a.tocsr()


def threshold_graph(sim: np.ndarray, avg_degree: float = 10) -> sparse.csr_matrix:
    """Links every pair above one global similarity cut-off, set so the average book has
    `avg_degree` links. Dense topics get many links, isolated books get none."""
    n = len(sim)
    iu = np.triu_indices(n, 1)
    vals = sim[iu]
    m = int(avg_degree * n / 2)
    keep = np.argpartition(-vals, m)[:m]
    a = sparse.csr_matrix((np.ones(m), (iu[0][keep], iu[1][keep])), shape=(n, n))
    return (a + a.T).tocsr()
