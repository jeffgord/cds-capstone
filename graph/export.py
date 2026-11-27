"""Exports the graph variants for the UI's graph page (web/graph.html) to web/graph-data/.

- index.json: the books (title, author, cover, LCC main classes), class names, and the variants with
  their scores from graph/cache/results.json
- {variant}.json: a 2D position and the 10 nearest books (best first) for every book

Positions are t-SNE on that variant's own similarities, so books the variant finds similar sit
together as islands. The LCC network is exported the same way, as the reference to compare against.

Run: python graph/export.py   (after experiments.py; ~5 min, mostly the t-SNE layouts)
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from sklearn.manifold import TSNE

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learn  # noqa: E402
import similarity as S  # noqa: E402
from features import CACHE, MODELS, load_records, mean_by_owner  # noqa: E402
from metrics import B, Labels  # noqa: E402

OUT = HERE.parent / "web" / "graph-data"
K = 10
MEASURES = {"cosine": "Cosine", "whitened cosine": "Whitened cosine", "CSLS": "CSLS (hub-corrected)",
            "shared neighbours": "Shared neighbors", "chunk max-sim": "Chunk max-sim"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def layout(sim: np.ndarray) -> list[list[int]]:
    """t-SNE on 'how far apart' (the top similarity minus each similarity), scaled to 0..1000. Scaled by
    the 1st to 99th percentile so a few far-off books don't squeeze everything else into the middle."""
    d = sim.max() - sim
    np.fill_diagonal(d, 0)
    xy = TSNE(2, metric="precomputed", init="random", perplexity=30, random_state=0).fit_transform(d)
    lo, hi = np.percentile(xy, 1, axis=0), np.percentile(xy, 99, axis=0)
    xy = ((xy - lo) / (hi - lo).clip(1e-9)).clip(-0.02, 1.02)
    return np.round(xy * 1000).astype(int).tolist()


def neighbours(sim: np.ndarray) -> list[list[int]]:
    """Each book's K most similar books, most similar first."""
    s = sim.copy()
    np.fill_diagonal(s, -np.inf)
    top = np.argpartition(-s, K, axis=1)[:, :K]
    order = np.argsort(-np.take_along_axis(s, top, axis=1), axis=1)
    return np.take_along_axis(top, order, axis=1).tolist()


def variants(labels: Labels) -> list[dict]:
    """(model, measure, key, similarity) for every variant the page offers."""
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
    best = json.loads((CACHE / "results.json").read_text())["best_model"].split(" · ")[0]
    x = mean_by_owner(np.load(CACHE / f"chunks_{best}.npy"), owner, n)
    y = np.where(labels.primary >= 0, labels.primary, 0)
    train, _ = next(labels.splits(seeds=(0,)))
    out.append({"model": f"LDA on {best} (learned from LCC)", "measure": "cosine",
                "key": "LDA projection (learned from LCC) · cosine", "sim": learn.lda_projection(x, y, train)})
    lcc = S.lcc_similarity(labels.trails)
    # Books with the same call number tie exactly, and t-SNE collapses ties into single dots. For the
    # picture only, a little text similarity spreads them out by content; the neighbour lists stay pure LCC.
    out.append({"model": "LCC", "measure": "shared hierarchy levels", "key": "LCC itself (reference)",
                "sim": lcc, "layout_sim": lcc / lcc.max() + 0.25 * S.cosine(x)})
    return out


def book_list(records: list[dict], labels: Labels) -> list[dict]:
    """What the page's side card shows for a book, built with the API's own card()."""
    outline = B.load_lcc()
    out = []
    for rec, main in zip(records, labels.main):
        c = B.card(rec, outline)
        out.append({"id": int(rec["gutenberg_id"]), "title": c["title"],
                    "author": ", ".join(a["display"] for a in c["authors"][:2]),
                    "cover": c["cover_url"], "classes": sorted(main)})
    return out


def main() -> None:
    records = load_records()
    labels = Labels([int(r["gutenberg_id"]) for r in records])
    results = json.loads((CACHE / "results.json").read_text())
    scores = results["similarity"] | results["learning"]
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    listing = []
    for v in variants(labels):
        name = slug(v["key"])
        data = {"pos": layout(v.get("layout_sim", v["sim"])), "nb": neighbours(v["sim"])}
        (OUT / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
        listing.append({"file": name, "model": v["model"], "measure": MEASURES.get(v["measure"], v["measure"]),
                        "scores": scores.get(v["key"], {})})
        print("exported", v["key"])
    outline = B.load_lcc()
    classes = {c: B._clean_label((outline.get(c) or {}).get("title") or c)
               for c in sorted({c for m in labels.main for c in m})}
    index = {"books": book_list(records, labels), "classes": classes, "variants": listing,
             "random": results["similarity"]["random"]}  # the floor, for the leaderboard
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
