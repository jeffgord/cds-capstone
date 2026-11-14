# Building the evaluation set

The evaluation set pairs realistic search requests with human judgments of which books are useful for each request. It measures book discovery in the committed 1,000-book collection. The existing API tests check software behavior; they do not measure relevance.

## Start here

1. **Review the requests in `queries.csv` before looking at the candidate books.** There are 12 assistant-drafted requests: six topical searches, two pairs testing different meanings of a word, and two possible no-answer cases. Read each `intent`: it defines what would satisfy the request. Replace unrealistic wording or requests, and change `status` from `draft` to `reviewed` once you accept them. Missing coverage is a legitimate outcome; don't rewrite a request just because the system did poorly.
2. **Open `pilot/labels.csv` in a spreadsheet.** It contains 20 distinct candidate books per query, 240 rows total. Start by filtering to `q01`, `q02`, and `q03`: just 60 judgments. Scores and retrieval ranks are absent, and book order is shuffled within each query. Work from this worksheet rather than the ranked UI.
3. **Fill only `relevance`, `assessor`, and `notes`.** Use your initials in `assessor`. Add a brief reason or evidence reference in `notes`, particularly for borderline cases. Judge the whole book's usefulness for the stated request, not just shared words or the retrieved excerpt. Leave `relevance` blank if you cannot tell, and explain what needs checking in `notes`.
4. **Ask a teammate to independently label the same first 20 rows in a separate copy.** Compare after both finish. Discuss disagreements and refine the rubric before labeling the rest; keep both original copies. The request author or team should settle ambiguous intent consistently.
5. **Finish the pilot, then expand to 40–60 realistic queries.** This pilot is all development data. It is for learning the grading process and spotting failures, not choosing a production cutoff or reporting final generalization.

The initial worksheet uses the draft query text. If you change a request or its intent, regenerate into a new directory before grading that query; judgments cannot silently transfer to a different request. Status-only edits do not change relevance. Keep the query IDs and book IDs intact when sorting or exporting CSV.

## Relevance rubric

Ask: **Would I recommend this book as a useful source for this specific request?** A substantive chapter or section can be enough; the entire book need not be devoted to the topic. Judge usefulness as a source for research/discovery. Do not substitute agreement with the author's viewpoint for relevance.

| Grade | Meaning | Example for a request about how steam engines work |
|---|---|---|
| `2` | Useful: directly addresses the request with substantive information | Explains cylinders, pistons, valves, or conversion of steam pressure into motion |
| `1` | Tangential: meaningful related background, but does not substantially satisfy the request | Discusses the economic impact of steam power without explaining engine operation |
| `0` | Irrelevant: wrong topic/meaning or only an incidental mention | A journey mentioning arrival by steamship |
| blank | Unjudged or uncertain; not a negative label | The available text is insufficient to decide; record that in `notes` |

For binary measures such as Precision@5, the proposed rule is that only grade `2` counts as useful; graded nDCG can use all three levels. Agree this convention before comparing systems.

The worksheet supplies the title, subjects, Gutenberg's **auto-generated** summary, contents, and the retrieved passage when one exists. A summary is a lead, not definitive evidence. For unclear cases, inspect `book_record` in VS Code (the JSON includes all extracted fields) or follow `gutenberg_url` to the source book. A missing summary, introduction, or excerpt does not make a book irrelevant. You need not read every book cover to cover, but labels should have enough evidence to support the decision.

`no_answer_candidate` is a hypothesis, not a label. Judge those books normally. Finding no useful book among 20 retrieved candidates does **not** prove that none exists in the full collection. Keep corpus-level answerability unconfirmed until broader checking supports it; don't present these as verified no-answer cases yet.

## What happens after labeling

* Keep labels keyed by `(query_id, gutenberg_id)` so each book is judged once per request, regardless of how many passages match. The same book can earn different grades for different requests.
* The initial pool comes only from the current baseline. When testing enrichment and reranking, pool their top 20 unique books per query with the baseline results, deduplicate, shuffle, and label any new pairs. Retain existing judgments for unchanged requests. Do not treat unjudged candidates as grade `0` or present baseline-only judgments as a complete ground truth.
* Record each system's original ranks and scores separately. `pilot/run.json` contains these plus the exact request snapshot and corpus/index hashes; leave it closed while labeling. Do not insert known relevant books into a reranker's candidate list to make evaluation easier. The [Sentence Transformers evaluator documentation](https://www.sbert.net/docs/package_reference/cross_encoder/evaluation.html) explains how that would change what is being measured.
* Compare baseline, enriched fields, reranking, and the combination on the same judged requests. Use Precision@5 for how many first-page results are useful, nDCG@10 for ordering useful and tangential results, candidate Recall@20 against the known judged useful books, and query latency. Recall against a pooled set is not exhaustive corpus recall. Report unresolved judgments instead of silently counting them as irrelevant.
* For the expanded set, reserve about one third of queries as held-out test data **before tuning**. Keep related intents/paraphrases together using `intent_group`; distribute subjects and query types across the splits where possible. Use development results to choose fields, model, candidate count, and any threshold. Keep held-out results unseen until those choices are fixed. This 12-query pilot remains development data.
* Only then assess a cutoff using the chosen final scoring method. Report both irrelevant results retained and useful results hidden, including behavior on independently checked no-answer queries. A small pilot does not establish a reliable universal threshold.

## Files and regeneration

| File | Purpose |
|---|---|
| `queries.csv` | Editable requests and intended meanings; all initially `draft` / `pilot_dev` |
| `pilot/labels.csv` | Initial worksheet; all relevance labels intentionally blank |
| `pilot/run.json` | Baseline rankings, scores, query snapshot, and provenance; not for annotators |
| `prepare_labels.py` | Generates a fresh baseline worksheet using the existing local search backend |

The initial worksheet has already been generated. To regenerate after editing requests, run from the repo root in the project environment and choose a new output directory:

```sh
source .venv/bin/activate
HF_HUB_OFFLINE=1 python -m evaluation.prepare_labels --output-dir evaluation/pilot-v2
```

The script reads the existing index and book records, runs queries, and writes a new worksheet. It refuses to overwrite an existing output directory, protecting completed labeling work. It does not rebuild the index, alter the search app, assign relevance grades, or calculate quality metrics. The separate run file records the active model and index configuration.
