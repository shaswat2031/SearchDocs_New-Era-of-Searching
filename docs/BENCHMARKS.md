# SearchCore Benchmarks

This document captures how SearchCore's synthetic benchmark suite works and reports observed performance on a local machine.

## Benchmark Suite

[`searchcore/benchmark.py`](../searchcore/benchmark.py) generates a synthetic corpus (`_VOCAB_HEAD`, `_VOCAB_TAIL`, and embedded multi-word phrases), measures bulk SQLite WAL ingestion and restart snapshot recovery, verifies exact hit-count parity between serial and parallel search, and records latency percentiles across 6 query types:

1. `python`
2. `sqlite AND recovery`
3. `bm25 OR fastapi`
4. `"inverted index"`
5. `("search engine" OR "restart recovery") AND python`
6. `query AND NOT topic99`

## How to Run

```bash
python -m searchcore.benchmark --docs 2000 --iterations 20 --workers 2
```

### CLI Options

| Flag | Default | Description |
| :--- | :---: | :--- |
| `--docs` | `2000` | Number of synthetic documents to generate and index |
| `--iterations` | `20` | Repetitions across the 6-query suite (`queries_run = 6 * iterations`) |
| `--workers` | `2` | Number of spawned worker processes used by `ParallelSearchEngine` |

## Observed Results

Measured locally on Windows (`Python 3.12.10`) with `--docs 2000 --iterations 20 --workers 2`:

| Metric | Value |
| :--- | :--- |
| Corpus size | `2,000` documents |
| Total tokens | `114,800` tokens |
| Vocabulary size | `2,427` unique terms |
| Batch ingest (`add_documents_batch`) | `554.97 ms` (`3,603.8 docs/s`) |
| Restart recovery (`SearchEngine(db_path)`) | `186.78 ms` |

### Query Latency (120 queries per mode)

| Mode | Queries Run | Mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `serial` | 120 | 1.636 | 1.675 | 2.657 | 3.228 |
| `parallel(2w)` | 120 | 1.200 | 1.108 | 1.921 | 2.604 |

