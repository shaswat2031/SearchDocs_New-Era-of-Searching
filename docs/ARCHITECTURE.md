# SearchCore Architecture

This document summarizes how SearchCore indexes, stores, parses, ranks, and parallelizes queries across documents.

## 1. Indexing & Tokenization Pipeline

1. **Extraction (`searchcore/importer.py`)**
   - Supports `.txt`, `.md`, `.csv`, `.json`, `.log`, `.pdf` (via `pypdf`), and `.docx` (via `python-docx`).
2. **Tokenization (`searchcore/tokenizer.py`)**
   - Applies Unicode NFKC normalization, lowercases text, and extracts alphanumeric tokens (`[a-z0-9]+`).
   - `tokenize_document(title, content)` records positional indices for `title` first, skips one boundary slot, and indexes `content` afterward so adjacent phrase queries never accidentally span from title into body.
3. **In-Memory Positional Index (`searchcore/index.py`)**
   - Maintains `postings[term][doc_id] = [pos_0, pos_1, ...]` protected by an `RLock` and an incrementing `version` counter.

## 2. Okapi BM25 Scoring (`searchcore/bm25.py`)

For a document $d$ and matched term $t$:

- **Inverse Document Frequency (non-negative Robertson–Sparck Jones):**
  $$\text{IDF}(t) = \ln\left(\frac{N - df(t) + 0.5}{df(t) + 0.5} + 1\right)$$
- **Term Score Contribution (`k1 = 1.5`, `b = 0.75`):**
  $$\text{score}(d, t) = \text{IDF}(t) \cdot \frac{tf(t, d) \cdot (k_1 + 1)}{tf(t, d) + k_1 \cdot \left(1 - b + b \cdot \frac{|d|}{\text{avgdl}}\right)}$$

## 3. Boolean & Phrase Query Evaluation (`searchcore/query_parser.py`)

A recursive-descent parser produces an AST from `TermNode`, `PhraseNode`, `NotNode`, `AndNode`, and `OrNode`:
- Precedence: `(...)` / literals (`Term`, `"Phrase"`) > `NOT` > `AND` > `OR`.
- Exact phrases verify consecutive token positions (`pos + 1`, `pos + 2`, ...) against the positional postings lists.

## 4. SQLite WAL Persistence (`searchcore/storage.py`)

SQLite runs with `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and `PRAGMA foreign_keys=ON;` across two core tables:
- `documents(id, external_id, title, content, doc_length, metadata_json, created_at, updated_at)`
- `postings(term, doc_id, tf, positions)` with `PRIMARY KEY (term, doc_id)` and `ON DELETE CASCADE`

On startup, `SearchEngine` loads a snapshot from SQLite back into memory.

## 5. Multi-Process Parallel Search (`searchcore/parallel.py`)

1. Documents are sharded across `num_workers` spawned worker processes via `doc_id % num_workers`.
2. When `engine.version` changes, shard payloads sync to workers over `multiprocessing.Pipe`.
3. For queries containing phrases, a `COUNT_PHRASES` phase aggregates global phrase document frequencies across all shards before running `SEARCH_SHARD` with global `(N, avgdl, global_df)`, ensuring parallel BM25 scores match serial execution.
