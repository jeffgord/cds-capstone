"""How close a book similarity or graph is to the Library of Congress classification.

All scores are computed on held-out books only (the "test" side of a split), so methods that learn
from LCC labels are scored on books whose labels they never saw.

- p10_class / p10_sub: of each book's 10 most similar books, the share in the same LCC main class
  ("D") or subclass ("DS"). A ranking score, so it doesn't depend on how the graph is built.
- edge_class:   of the graph's links, the share joining books of the same main class.
- isolated:     share of books with no links at all.
- nmi:          communities found in the graph (Louvain) vs main classes, 0 to 1.
- vote_f1:      macro-F1 when each held-out book takes the class most common among its labelled
                neighbours. Small classes count as much as big ones.
"""
import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np
from scipy import sparse
from sklearn.metrics import f1_score, normalized_mutual_info_score
from sklearn.model_selection import StratifiedShuffleSplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api import books as B  # noqa: E402  (LCC trails come from the API's own code)

MIN_BOOKS = 10  # classes smaller than this can't be split into train and test reliably


class Labels:
    """Each book's LCC main classes, subclasses and full trails, plus which books can be scored."""

    def __init__(self, ids: list[int]):
        outline = B.load_lcc()
        codes = [json.loads((B.BOOKS_DIR / f"{g}.json").read_text(encoding="utf-8")).get("locc") or []
                 for g in ids]
        codes = [[c for c in cs if c] for cs in codes]
        self.main = [{c[0] for c in cs} for cs in codes]
        self.sub = [{B._parse_locc(c)[0] for c in cs} - {""} for cs in codes]
        self.trails = [[[t["code"] for t in B.lcc_trail(c, outline)] for c in cs] for cs in codes]
        first = [sorted(m)[0] if m else None for m in self.main]
        counts = {c: first.count(c) for c in set(first) if c}
        self.names = sorted(c for c, n in counts.items() if n >= MIN_BOOKS)
        self.primary = np.array([self.names.index(f) if f in self.names else -1 for f in first])
        self.scored = np.flatnonzero(self.primary >= 0)

    def splits(self, seeds=(0, 1, 2), train=0.3):
        """Stratified (train, test) index arrays; 30% of labels known, like a semi-supervised benchmark."""
        for seed in seeds:
            split = StratifiedShuffleSplit(1, train_size=train, random_state=seed)
            tr, te = next(split.split(self.scored, self.primary[self.scored]))
            yield self.scored[tr], self.scored[te]


def precision_at_10(sim: np.ndarray, sets: list[set], test: np.ndarray) -> float:
    """Share of each test book's 10 nearest test books that share a label with it."""
    s = sim[np.ix_(test, test)].copy()
    np.fill_diagonal(s, -np.inf)
    nb = np.argpartition(-s, 10, axis=1)[:, :10]
    hits = [[bool(sets[test[i]] & sets[test[j]]) for j in row] for i, row in enumerate(nb)]
    return float(np.mean(hits))


def edge_agreement(a: sparse.csr_matrix, sets: list[set], test: np.ndarray) -> float:
    r, c = sparse.triu(a[test][:, test], 1).nonzero()
    return float(np.mean([bool(sets[test[i]] & sets[test[j]]) for i, j in zip(r, c)])) if len(r) else 0.0


def isolated(a: sparse.csr_matrix, test: np.ndarray) -> float:
    return float(np.mean(np.asarray(a[test][:, test].sum(1)).ravel() == 0))


def community_nmi(a: sparse.csr_matrix, labels: Labels, test: np.ndarray) -> float:
    g = nx.from_scipy_sparse_array(a[test][:, test])
    comm = np.zeros(len(test), dtype=int)
    for i, nodes in enumerate(nx.community.louvain_communities(g, seed=0)):
        comm[list(nodes)] = i
    return float(normalized_mutual_info_score(labels.primary[test], comm))


def vote_f1(a: sparse.csr_matrix, labels: Labels, train: np.ndarray, test: np.ndarray) -> float:
    onehot = np.zeros((a.shape[0], len(labels.names)))
    onehot[train, labels.primary[train]] = 1
    majority = np.bincount(labels.primary[train], minlength=len(labels.names)).argmax()
    votes = a[test] @ onehot
    pred = np.where(votes.sum(1) > 0, votes.argmax(1), majority)  # no labelled neighbour: guess the biggest class
    return float(f1_score(labels.primary[test], pred, average="macro"))


def score(sim: np.ndarray, a: sparse.csr_matrix, labels: Labels, train: np.ndarray, test: np.ndarray) -> dict:
    """Every metric for one similarity matrix and the graph built from it, on one split."""
    return {"p10_class": precision_at_10(sim, labels.main, test),
            "p10_sub": precision_at_10(sim, labels.sub, test),
            "edge_class": edge_agreement(a, labels.main, test),
            "isolated": isolated(a, test),
            "nmi": community_nmi(a, labels, test),
            "vote_f1": vote_f1(a, labels, train, test)}
