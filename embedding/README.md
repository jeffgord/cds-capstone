**Pure** semantic retrieval system built over 1,000 English nonfiction Project Gutenberg books using **LangChain**, **FAISS**, and **`BAAI/bge-base-en-v1.5`**. Rather than relying on surface-level keyword matching, the engine indexes both book-level catalog metadata/summaries and sampled in-text passages so users can search by theme, concept, or narrative situation.

---

## Architecture & What's Done

### 1. Multi-Granularity Document Indexing (6,896 Vectors)
Each book JSON in `data/books/` is expanded into up to **7 dense vector documents** inside `embedding/create_embed_document.py`:
* **1 Catalog & Summary Document (`doc_type="summary"`):** Combines `title`, `contributors`, `subjects`, mapped Library of Congress (`locc`) classifications, and `description` via `format_book()`.
* **Up to 6 Passage Documents (`doc_type="passage"`):** Indexes each ~400-character excerpt from `book["passages"]` (971 of the 1,000 books contain all 6 passages), prefixed with the book's `Title` and `Subjects` so individual snippets retain book-level context.

### 2. Embedding & Vector Store Setup
* **Model:** `BAAI/bge-base-en-v1.5` (upgraded from `all-MiniLM-L6-v2`'s 384 dimensions to 768 dimensions, 512-token context window) with L2 normalization enabled (`normalize_embeddings=True`).
* **Index Persistence:** Built once via `test_script.py` and saved locally to `gutenberg_faiss_test/` for sub-second query loading in `search_test.py`.

### 3. Book-Level Deduplication & Similarity Scoring
* **Deduplication (`search_books`):** Fetches `top_k * 5` candidate vectors from FAISS and filters duplicate `gutenberg_id` hits so multiple passages from the *same* book do not crowd out distinct books covering the same topic.
* **Normalized Similarity Readout:** Converts FAISS squared L2 distances on unit vectors into intuitive cosine similarity scores (`1.0 - l2_distance / 2.0`), ranked from highest (`1.0`) to lowest (`0.0`).
* **Provenance Tracking:** Displays whether each result matched via `summary` or `passage`, along with the triggering snippet.

---

## Repository Structure

```text
.
├── data/
│   └── books/                     # 1,000 pre-ingested Project Gutenberg JSON records
├── embedding/
│   ├── preprocess.py              # LoCC mapping and format_book() metadata formatter
│   └── create_embed_document.py   # Builds summary + passage LangChain Documents
├── gutenberg_faiss_test/          # Saved FAISS vector index (6,896 vectors)
├── test_script.py                 # Builds and saves the FAISS index from data/books/
└── search_test.py                 # Loads FAISS index and runs deduplicated semantic queries