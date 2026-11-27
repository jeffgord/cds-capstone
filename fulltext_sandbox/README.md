# Full-Text FAISS Sandbox

Experimental scripts and workflow for building, searching, and evaluating a full-text FAISS index (`BAAI/bge-base-en-v1.5`) over the 1,000-book Gutenberg collection without modifying baseline/shared code or cluttering the repository root.

## Directory & Related Files

```text
<repo_root>/
├── fulltext_sandbox/
│   ├── README.md
│   ├── build_faiss_fulltext_sandbox.py     # Builds full-text FAISS index (GPU recommended)
│   ├── search_cli_fulltext_sandbox.py    # Terminal search against full-text index (CPU ok)
│   └── eval_samples_fulltext_sandbox.py  # Evaluates full-text index on sample_eval/seed_eval.jsonl
├── embedding/
│   └── create_embed_document_fulltext.py # Builds summary, passage, and full_text_chunk docs
├── ingestion/
│   ├── clean_full_texts_sandbox.py       # Cleans raw full-text files
│   └── build_fulltext_records_sandbox.py # Builds enriched book JSON records
├── data/                                 # Local/scratch data (keep out of Git if large)
│   ├── raw/
│   ├── cleaned/
│   └── enriched_books/
└── sample_eval/
    ├── seed_eval.jsonl
    ├── eval_results.json                 # Baseline eval output
    └── eval_results_fulltext.json        # Full-text sandbox eval output
```

## Run Commands

Run all commands from the **repository root**:

### Build the Full-Text FAISS Index (GPU Recommended)

```bash
python fulltext_sandbox/build_faiss_fulltext_sandbox.py \
  --batch-size 128 \
  --index-dir "$SCRATCH/gutenberg_faiss_fulltext"
  
### Search from the Terminal (CPU Sufficient)
```bash
python fulltext_sandbox/search_cli_fulltext_sandbox.py "home remedies and herbal medicine" -k 5
```

### Run Sample Evaluation
```bash
python fulltext_sandbox/eval_samples_fulltext_sandbox.py
```

This writes results to sample_eval/eval_results_fulltext.json without overwriting sample_eval/eval_results.json.