# Book graph (experiment)

A graph of the 1,000 books where each book links to the books whose embeddings are closest to it. It's an experiment, separate from the search app: nothing here is used by `api/` or `web/` yet.

The question is whether embedding similarity alone groups books the way librarians do. Library of Congress (LCC) main classes are never used to build the graph, only to test it, the way labels are used in graph ML benchmarks.

```sh
python graph/features.py     # one vector per book, three ways (~2 min), saved to graph/cache/ (gitignored)
python graph/evaluate.py     # builds the k-NN graph and scores it against LCC (~10 s); --k sets neighbours
```

## Setup

- **Nodes:** books. **Edges:** each book's k nearest books by cosine similarity, kept if either book picked the other, weighted by the similarity.
- **Node vectors, three views:**
  - `summary`: the summary vector from the search index. It embeds the text "Classification: <LCC label>", so scores on it are an upper bound, not a fair test.
  - `passages`: the mean of the book's passage vectors from the index. Their header includes Gutenberg bookshelves, which overlap with LCC.
  - `text`: the book's own passages plus Gutenberg's description, re-embedded with no title, subjects or class. **This is the leak-free view.**
- **Labels:** LCC main class (the first letter of the call number). A book can have several. Classes with under 10 books are left out: 988 books in 18 classes remain.
- **Task:** node classification. The class is known for 30% of books, stratified, and predicted for the rest. Results are averaged over 5 splits. A prediction counts as right if it's any of the book's classes. Macro-F1 uses the book's first class, so small classes count as much as big ones.

## Results (k = 10)

| | summary (leaky) | passages | text (clean) |
|---|---|---|---|
| Linked books share a class | 56% | 53% | 50% |
| Random pairs share a class | 12% | 12% | 12% |
| majority, acc / F1 | .246 / .022 | .246 / .022 | .246 / .022 |
| logreg on the vector, no graph | .731 / .520 | .684 / .458 | .664 / .438 |
| neighbour vote | .697 / .586 | .661 / .527 | .638 / .510 |
| label propagation | .621 / .416 | .598 / .360 | .599 / .380 |
| SGC (2-hop smoothing + logreg) | .645 / .373 | .605 / .332 | .609 / .365 |

What it says, with no relevance labels behind it, so treat it as exploratory:

- **The graph tracks LCC.** With no metadata at all, two linked books share a main class 50% of the time vs 12% for random pairs, about 4x. The leak in the summary vectors adds only about 6 points.
- **The neighbour vote is best on small classes.** Macro-F1 is .510 vs .438 for logreg, with slightly lower accuracy (.638 vs .664). Linked books help most where a class has few examples.
- **Multi-hop methods do worse than one hop.** Label propagation and SGC smooth over several hops, and with 18 unbalanced classes the big classes (D, B, E/F) flood the small ones. They get worse as k grows: propagation F1 is .448 at k = 5 and .250 at k = 20. Homophily drops too (55% at k = 5, 45% at k = 20), so the closest few neighbours carry most of the signal.

## Next

- Tune k and alpha, or use a GNN with learned weights, if multi-hop is worth pursuing.
- Mismatches between the graph and LCC are worth reading by hand. Some will be graph errors, but some will be books that LCC files apart and that really are about the same thing. Those are the interesting ones for discovery.
- A "related books" list (the top neighbours in the `text` view) is the simplest way to show this in the UI.
