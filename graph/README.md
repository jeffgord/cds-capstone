# Book graph (experiment)

A graph of the 1,000 books where each book links to the books most similar to it. The question is which way of measuring similarity groups books most like the Library of Congress Classification (LCC). LCC is never used to build the graph, only to score it, the way labels are used in graph ML benchmarks. The search app doesn't use any of this. The UI shows it on a separate page, `web/graph.html`.

```sh
python graph/features.py      # book vectors from 4 embedding models (~6 min first time), cached in graph/cache/
python graph/experiments.py   # scores every variant, writes graph/results.md (~2 min)
python graph/export.py        # t-SNE layouts + neighbour lists for web/graph.html, in web/graph-data/ (~5 min)
```

## What's compared

- **Book text, leak-free:** each book's passages plus Gutenberg's description, embedded with no title, subjects or class. The search index's own summary vectors embed the text "Classification: <LCC label>", so they're included only as a leaky upper bound (`index summary`).
- **Embedding models:** `bge-base` (the search index's model), `bge-small`, `minilm` (all-MiniLM-L6-v2) and `mpnet` (all-mpnet-base-v2).
- **Similarity measures:**
  - cosine
  - whitened cosine: removes the direction all embeddings share
  - CSLS: down-weights "hub" books that are close to everything
  - shared neighbours: two books are close if the same books surround them
  - chunk max-sim: compares passage to passage instead of averaging first
  - TF-IDF word overlap, as a baseline only
- **Graph construction:** kNN at k = 5, 10 and 20, mutual kNN, and a global similarity threshold.
- **Learning from labels:** with 30% of books' classes known, an LDA projection learned from LCC, and GCN, GraphSAGE and GAT classifiers against an MLP that sees no graph.
- **Reference:** the LCC network itself, where books are linked by how many levels of the LCC hierarchy they share.

## Scores

All scores are on held-out books, averaged over 3 stratified splits. That's 988 books in 18 main classes with at least 10 books each.

- `p10_class` / `p10_sub`: of a book's 10 most similar books, the share in the same LCC main class / subclass
- `edge_class`: the share of graph links that join books of the same main class
- `nmi`: how well communities found in the graph (Louvain) line up with the main classes
- `vote_f1`: macro-F1 when a book's class is guessed from its labelled neighbours

## Findings (full tables in [results.md](results.md))

These are exploratory. LCC is one librarian's view of a book, not ground truth for "similar".

- **Closest to LCC: `mpnet` with shared neighbours.** p10_class is .578, against .990 for LCC itself and .120 for random links. On text alone it beats the leaky summary vectors (.559).
- **Shared neighbours helps every model,** by 2 to 4 points over plain cosine. CSLS helps a little. Chunk max-sim is mixed. Whitening only ties cosine, and only at 16 dimensions; with more it overfits 1,000 books.
- **The search index's model (`bge-base`, cosine, .509) barely beats TF-IDF word overlap (.500)** at matching LCC. `mpnet` does better (.538 cosine). Worth trying `mpnet` in the search index.
- **How the graph is built matters less than the similarity.** A global threshold gives the cleanest links (70% same class) and the best communities (NMI .496), but leaves 10% of books with no links. kNN keeps every book connected.
- **The graph carries information beyond the vectors.** GraphSAGE reaches macro-F1 .572 against .529 for the same network with no graph. GCN and GAT gain about 2 points. LDA learned from LCC barely moves p10_class (.584) and lowers the subclass score, so it learns the main classes and blurs the finer ones.
