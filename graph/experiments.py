"""Runs every book-graph variant and scores how close each one is to the LCC classification.

Three studies, each averaged over 3 stratified splits (30% of LCC labels known, scored on the rest):
1. Similarity: embedding model x similarity measure, all as a 10-nearest-neighbour graph.
2. Graph construction: kNN at several k, mutual kNN and a global threshold, on the best similarity.
3. Learning from the known labels: an LCC-trained projection, and GNNs vs an MLP with no graph.

Writes graph/results.md (the tables) and graph/cache/results.json.
Run: python graph/experiments.py   (needs graph/cache/ from features.py; ~3 min)
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learn  # noqa: E402
import similarity as S  # noqa: E402
from features import CACHE, MODELS, mean_by_owner  # noqa: E402
from metrics import Labels, score  # noqa: E402

COLUMNS = ["p10_class", "p10_sub", "edge_class", "isolated", "nmi", "vote_f1"]


def similarities(labels: Labels) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Every (similarity matrix, vectors) to compare. Vectors are kept for the GNN study."""
    owner = np.load(CACHE / "owner.npy")
    n = len(labels.primary)
    out = {}
    for short in MODELS:
        chunks = np.load(CACHE / f"chunks_{short}.npy")
        x = mean_by_owner(chunks, owner, n)
        cos = S.cosine(x)
        out[f"{short} · cosine"] = (cos, x)
        out[f"{short} · whitened cosine"] = (S.whitened_cosine(x), x)
        out[f"{short} · CSLS"] = (S.csls(cos), x)
        out[f"{short} · shared neighbours"] = (S.shared_neighbours(cos), x)
        out[f"{short} · chunk max-sim"] = (S.chunk_maxsim(chunks, owner, n), x)
    for view in ("index_summary", "index_passages"):
        x = np.load(CACHE / f"{view}.npy")
        out[f"{view.replace('_', ' ')} · cosine"] = (S.cosine(x), x)
    texts = json.loads((CACHE / "texts.json").read_text())
    out["TF-IDF word overlap · cosine"] = (S.tfidf_cosine(texts, owner, n), None)
    rng = np.random.default_rng(0).random((n, n))
    out["random"] = ((rng + rng.T) / 2, None)
    out["LCC itself (reference)"] = (S.lcc_similarity(labels.trails), None)
    return out


def averaged(fn, labels: Labels) -> dict:
    rows = [fn(train, test) for train, test in labels.splits()]
    return {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}


def study_similarity(sims, labels) -> dict:
    return {name: averaged(lambda tr, te: score(sim, S.knn_graph(sim, 10), labels, tr, te), labels)
            for name, (sim, _) in sims.items()}


def study_graphs(sim, labels) -> dict:
    builders = {"kNN k=5": lambda: S.knn_graph(sim, 5), "kNN k=10": lambda: S.knn_graph(sim, 10),
                "kNN k=20": lambda: S.knn_graph(sim, 20), "mutual kNN k=10": lambda: S.knn_graph(sim, 10, True),
                "threshold, 10 links per book on average": lambda: S.threshold_graph(sim, 10)}
    return {name: averaged(lambda tr, te, b=b(): score(sim, b, labels, tr, te), labels)
            for name, b in builders.items()}


def study_learning(sim, x, labels) -> dict:
    y = np.where(labels.primary >= 0, labels.primary, 0)  # unscored books are never in train or test
    a = S.knn_graph(sim, 10)
    out = {"LDA projection (learned from LCC) · cosine": averaged(
        lambda tr, te: score(lda := learn.lda_projection(x, y, tr), S.knn_graph(lda, 10), labels, tr, te), labels)}
    for kind in ("mlp", "gcn", "sage", "gat"):
        out[f"{kind.upper()} classifier"] = averaged(
            lambda tr, te: {"vote_f1": learn.train_gnn(kind, x, a, y, tr, te)}, labels)
    return out


def table(rows: dict, cols: list[str]) -> str:
    head = "| | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols) + "\n"
    return head + "".join(f"| {name} | " + " | ".join(f"{r[c]:.3f}" if c in r else "" for c in cols) + " |\n"
                          for name, r in rows.items())


def main() -> None:
    labels = Labels(json.loads((CACHE / "ids.json").read_text()))
    sims = similarities(labels)
    sim_rows = study_similarity(sims, labels)
    fair = {k: v for k, v in sim_rows.items() if not k.startswith(("index summary", "LCC", "random"))}
    best = max(fair, key=lambda k: fair[k]["p10_class"])
    best_sim, best_x = sims[best]
    best_model = max((k for k in fair if k.endswith("· cosine") and sims[k][1] is not None),
                     key=lambda k: fair[k]["p10_class"])
    graph_rows = study_graphs(best_sim, labels)
    learn_rows = study_learning(sims[best_model][0], sims[best_model][1], labels)
    results = {"similarity": sim_rows, "graphs": graph_rows, "learning": learn_rows,
               "best": best, "best_model": best_model, "n_books": int(len(labels.scored)),
               "n_classes": len(labels.names)}
    (CACHE / "results.json").write_text(json.dumps(results, indent=1))
    ranked = dict(sorted(sim_rows.items(), key=lambda kv: -kv[1]["p10_class"]))
    (HERE / "results.md").write_text(
        f"# Book graph results\n\nGenerated by `graph/experiments.py`. {results['n_books']} books in "
        f"{results['n_classes']} LCC main classes; 3 splits, 30% of labels known, scored on the rest.\n\n"
        f"## 1. Similarity (10-NN graph), sorted by p10_class\n\n{table(ranked, COLUMNS)}\n"
        f"## 2. Graph construction on `{best}`\n\n{table(graph_rows, COLUMNS)}\n"
        f"## 3. Learning from known labels, on `{best_model}`\n\n{table(learn_rows, COLUMNS)}")
    print((HERE / "results.md").read_text())


if __name__ == "__main__":
    main()
