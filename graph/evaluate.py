"""Builds a book graph from embeddings and checks it against the Library of Congress classes.

Each book is a node. Each book links to its k most similar books (cosine on the vectors from
features.py). LCC main classes are never used to build the graph, only to test it:

1. Homophily: how often two linked books share an LCC main class, vs two random books.
2. Node classification: hide the class of 70% of books and predict it from the 30% that are known.
   - majority:   always the most common class (the floor)
   - logreg:     the book's own vector only, no graph
   - vote:       the classes of a book's known neighbours, weighted by similarity
   - propagate:  label propagation, so classes spread through several hops
   - sgc:        vectors smoothed over 2 hops of the graph, then logistic regression

If the graph models helped over logreg, the links carry signal the vectors alone don't.

Run: python graph/evaluate.py [--k 10]   (needs graph/cache/ from features.py; ~10 s)
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedShuffleSplit

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(__file__).resolve().parent / "cache"
VIEWS = ["summary", "passages", "text"]
MIN_BOOKS = 10   # classes smaller than this can't be split into train and test reliably
TRAIN = 0.3
SEEDS = range(5)


def load_classes(ids: list[int]) -> list[set[str]]:
    """Each book's LCC main classes (first letters of its call numbers)."""
    out = []
    for g in ids:
        rec = json.loads((ROOT / "data" / "books" / f"{g}.json").read_text(encoding="utf-8"))
        out.append({c[0] for c in rec.get("locc") or [] if c})
    return out


def knn_graph(x: np.ndarray, k: int) -> sparse.csr_matrix:
    """Symmetric k-nearest-neighbour graph, weighted by cosine similarity."""
    sim = x @ x.T
    np.fill_diagonal(sim, -np.inf)
    nbrs = np.argsort(-sim, axis=1)[:, :k]
    rows = np.repeat(np.arange(len(x)), k)
    a = sparse.csr_matrix((sim[rows, nbrs.ravel()].clip(0), (rows, nbrs.ravel())), shape=sim.shape)
    return a.maximum(a.T)  # an edge if either book picked the other


def homophily(a: sparse.csr_matrix, classes: list[set[str]], seed: int = 0) -> tuple[float, float]:
    """Share of edges whose two books share a class, and the same share for random pairs."""
    r, c = sparse.triu(a, 1).nonzero()
    linked = np.mean([bool(classes[i] & classes[j]) for i, j in zip(r, c)])
    rng = np.random.default_rng(seed)
    pi, pj = rng.integers(0, len(classes), 20000), rng.integers(0, len(classes), 20000)
    rand = np.mean([bool(classes[i] & classes[j]) for i, j in zip(pi, pj) if i != j])
    return float(linked), float(rand)


def norm_adj(a: sparse.csr_matrix) -> sparse.csr_matrix:
    """D^-1/2 (A + I) D^-1/2, the usual GCN normalisation."""
    a = a + sparse.eye(a.shape[0])
    d = np.asarray(a.sum(1)).ravel() ** -0.5
    return sparse.diags(d) @ a @ sparse.diags(d)


def predict_all(x, a, y, train, n_cls) -> dict[str, np.ndarray]:
    """Class scores for every node from each method, trained on the `train` nodes only."""
    onehot = np.zeros((len(y), n_cls))
    onehot[train, y[train]] = 1
    s = norm_adj(a)
    f = onehot.copy()
    for _ in range(50):  # label propagation (Zhou et al. 2004), alpha = 0.9
        f = 0.9 * (s @ f) + 0.1 * onehot
    x_sgc = s @ (s @ x)

    def logreg(feats):
        m = LogisticRegression(max_iter=2000, C=10).fit(feats[train], y[train])
        out = np.zeros((len(y), n_cls))
        out[:, m.classes_] = m.predict_proba(feats)
        return out

    majority = np.zeros((len(y), n_cls))
    majority[:, np.bincount(y[train], minlength=n_cls).argmax()] = 1
    return {"majority": majority, "logreg": logreg(x), "vote": a @ onehot + 1e-9 * majority,
            "propagate": f, "sgc": logreg(x_sgc)}


def evaluate(x, a, classes) -> tuple[dict[str, tuple[float, float]], int, int]:
    """Mean accuracy and macro-F1 per method over SEEDS, plus how many books and classes were scored. A prediction counts as right if it is
    any of the book's classes (books can have several); macro-F1 uses the first class."""
    keep_names = [n for n, c in zip(*np.unique([sorted(c)[0] for c in classes if c], return_counts=True))
                  if c >= MIN_BOOKS]
    names = {n: i for i, n in enumerate(keep_names)}
    nodes = np.array([i for i, c in enumerate(classes) if c and sorted(c)[0] in names])
    y_all = np.full(len(classes), -1)
    y_all[nodes] = [names[sorted(classes[i])[0]] for i in nodes]
    scores: dict[str, list[tuple[float, float]]] = {}
    for seed in SEEDS:
        split = StratifiedShuffleSplit(1, train_size=TRAIN, random_state=seed)
        tr, te = next(split.split(nodes, y_all[nodes]))
        train, test = nodes[tr], nodes[te]
        y = y_all.copy()
        y[y < 0] = 0  # unlabeled nodes still sit in the graph but are never trained or scored
        for method, p in predict_all(x, a, y, train, len(names)).items():
            pred = p[test].argmax(1)
            acc = np.mean([keep_names[q] in classes[i] for q, i in zip(pred, test)])
            scores.setdefault(method, []).append((acc, f1_score(y[test], pred, average="macro")))
    return {m: tuple(np.mean(v, axis=0)) for m, v in scores.items()}, len(nodes), len(names)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10)
    k = ap.parse_args().k
    ids = json.loads((CACHE / "ids.json").read_text())
    classes = load_classes(ids)
    for view in VIEWS:
        x = np.load(CACHE / f"{view}.npy")
        a = knn_graph(x, k)
        linked, rand = homophily(a, classes)
        res, n, c = evaluate(x, a, classes)
        print(f"\n== {view} (k={k}, {a.nnz // 2} edges, {n} books in {c} classes)")
        print(f"homophily: linked books share a class {linked:.0%} of the time, random pairs {rand:.0%}")
        for method, (acc, f1) in res.items():
            print(f"  {method:<10} acc {acc:.3f}  macro-F1 {f1:.3f}")


if __name__ == "__main__":
    main()
