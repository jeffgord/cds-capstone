"""Exports the graph variants for the UI's graph page (web/graph.html) to web/graph-data/.

Each variant is a 10-nearest-neighbour graph with a precomputed 2D layout, so the browser only draws.
- index.json: the books (id, title, LCC main classes), the class names, and the list of variants
  with their scores from graph/cache/results.json
- {variant}.json: node positions and edges

Positions are a force-directed layout of that variant's own graph, so clusters show up where the
graph has them. The LCC network is exported the same way, as the reference to compare against.

Run: python graph/export.py   (after experiments.py; ~2 min, mostly the layouts)
"""
import json
import re
import sys
from pathlib import Path

import networkx as nx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learn  # noqa: E402
import similarity as S  # noqa: E402
from features import CACHE, MODELS, mean_by_owner, load_records  # noqa: E402
from metrics import B, Labels  # noqa: E402

OUT = HERE.parent / "web" / "graph-data"
MEASURES = {"cosine": "Cosine", "whitened cosine": "Whitened cosine", "CSLS": "CSLS (hub-corrected)",
            "shared neighbours": "Shared neighbours", "chunk max-sim": "Chunk max-sim"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def layout(sim: np.ndarray) -> list[list[int]]:
    """Force-directed layout of the 10-NN graph, scaled to 0..1000 so the files stay small."""
    a = S.knn_graph(sim, 10)
    pos = nx.spring_layout(nx.from_scipy_sparse_array(a), seed=0, iterations=150)
    xy = np.array([pos[i] for i in range(len(sim))])
    xy = (xy - xy.min(0)) / (xy.max(0) - xy.min(0)).clip(1e-9)
    return np.round(xy * 1000).astype(int).tolist(), a


def variants(labels: Labels) -> list[dict]:
    """(group, model, measure, similarity) for every variant the page offers."""
    owner = np.load(CACHE / "owner.npy")
    n = len(labels.primary)
    out = []
    for short in MODELS:
        chunks = np.load(CACHE / f"chunks_{short}.npy")
        x = mean_by_owner(chunks, owner, n)
        cos = S.cosine(x)
        sims = {"cosine": cos, "whitened cosine": S.whitened_cosine(x), "CSLS": S.csls(cos),
                "shared neighbours": S.shared_neighbours(cos), "chunk max-sim": S.chunk_maxsim(chunks, owner, n)}
        out += [{"model": short, "measure": m, "key": f"{short} · {m}", "sim": s} for m, s in sims.items()]
    for view in ("index_summary", "index_passages"):
        name = view.replace("_", " ")
        out.append({"model": name, "measure": "cosine", "key": f"{name} · cosine",
                    "sim": S.cosine(np.load(CACHE / f"{view}.npy"))})
    texts = json.loads((CACHE / "texts.json").read_text())
    out.append({"model": "TF-IDF word overlap", "measure": "cosine", "key": "TF-IDF word overlap · cosine",
                "sim": S.tfidf_cosine(texts, owner, n)})
    best = json.loads((CACHE / "results.json").read_text())["best_model"]
    x = mean_by_owner(np.load(CACHE / f"chunks_{best.split(' · ')[0]}.npy"), owner, n)
    y = np.where(labels.primary >= 0, labels.primary, 0)
    train, _ = next(labels.splits(seeds=(0,)))
    out.append({"model": f"LDA on {best.split(' · ')[0]} (learned from LCC)", "measure": "cosine",
                "key": "LDA projection (learned from LCC) · cosine", "sim": learn.lda_projection(x, y, train)})
    out.append({"model": "LCC", "measure": "shared hierarchy levels", "key": "LCC itself (reference)",
                "sim": S.lcc_similarity(labels.trails)})
    return out


def main() -> None:
    records = load_records()
    ids = [int(r["gutenberg_id"]) for r in records]
    labels = Labels(ids)
    results = json.loads((CACHE / "results.json").read_text())
    scores = results["similarity"] | results["learning"]
    OUT.mkdir(exist_ok=True)
    listing = []
    for v in variants(labels):
        pos, a = layout(v["sim"])
        r, c = np.triu(a.toarray(), 1).nonzero()
        name = slug(v["key"])
        (OUT / f"{name}.json").write_text(json.dumps({"pos": pos, "edges": np.c_[r, c].ravel().tolist()},
                                                     separators=(",", ":")))
        listing.append({"file": name, "model": v["model"], "measure": MEASURES.get(v["measure"], v["measure"]),
                        "scores": scores.get(v["key"], {})})
        print("exported", v["key"])
    books = [{"id": g, "title": rec.get("title") or "Untitled", "classes": sorted(m)}
             for g, rec, m in zip(ids, records, labels.main)]
    outline = B.load_lcc()
    classes = {c: B._clean_label((outline.get(c) or {}).get("title") or c)
               for c in sorted({c for m in labels.main for c in m})}
    (OUT / "index.json").write_text(json.dumps({"books": books, "classes": classes, "variants": listing},
                                               separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
