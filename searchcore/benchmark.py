"""Performance benchmark suite for SearchCore (indexing, recovery, serial vs parallel search)."""

from __future__ import annotations

import argparse
import math
import random
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from searchcore.index import SearchEngine
from searchcore.parallel import ParallelSearchEngine

_VOCAB_HEAD = [
    "search", "engine", "sqlite", "python", "index", "document", "query", "ranking",
    "bm25", "inverted", "phrase", "boolean", "parallel", "process", "shard", "worker",
    "storage", "recovery", "latency", "throughput", "fastapi", "pytest", "memory", "disk",
]

_VOCAB_TAIL = [f"topic{i}" for i in range(400)]

_PHRASES = [
    "inverted index",
    "search engine",
    "restart recovery",
    "phrase matching",
    "relevance ranking",
    "parallel search",
]


@dataclass(frozen=True)
class QueryLatencySummary:
    mode: str
    queries_run: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, math.ceil(pct * len(sorted_values)) - 1))
    return sorted_values[idx]


def _generate_corpus(num_docs: int, seed: int = 42) -> list[dict[str, object]]:
    rng = random.Random(seed)
    docs: list[dict[str, object]] = []
    for i in range(num_docs):
        words = [rng.choice(_VOCAB_HEAD) for _ in range(18)]
        words.extend(rng.choice(_VOCAB_TAIL) for _ in range(36))
        if i % 5 == 0:
            words.append(rng.choice(_PHRASES))
        rng.shuffle(words)
        docs.append(
            {
                "external_id": f"bench-{i}",
                "title": f"Document {i} {rng.choice(_VOCAB_HEAD)}",
                "content": " ".join(words),
                "metadata": {"shard_hint": i % 4},
            }
        )
    return docs


def run_benchmark(
    num_docs: int = 2000,
    iterations: int = 25,
    num_workers: int = 2,
) -> dict[str, object]:
    """Run an end-to-end SearchCore benchmark and return structured metrics."""
    corpus = _generate_corpus(num_docs)
    queries = [
        "python",
        "sqlite AND recovery",
        "bm25 OR fastapi",
        '"inverted index"',
        '("search engine" OR "restart recovery") AND python',
        "query AND NOT topic99",
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bench.db"

        t0 = time.perf_counter()
        engine = SearchEngine(db_path=db_path)
        engine.add_documents_batch(corpus)
        ingest_ms = (time.perf_counter() - t0) * 1000.0
        engine.close()

        t_rec = time.perf_counter()
        recovered = SearchEngine(db_path=db_path)
        recovery_ms = (time.perf_counter() - t_rec) * 1000.0

        serial_times: list[float] = []
        parallel_times: list[float] = []

        try:
            for _ in range(iterations):
                for q in queries:
                    ts = time.perf_counter()
                    recovered.search(q, limit=10)
                    serial_times.append((time.perf_counter() - ts) * 1000.0)

            with ParallelSearchEngine(recovered, num_workers=num_workers) as parallel:
                # Warm up pipes and verify exact parity once.
                for q in queries:
                    s_res = recovered.search(q, limit=10)
                    p_res = parallel.search(q, limit=10)
                    assert p_res.total_hits == s_res.total_hits

                for _ in range(iterations):
                    for q in queries:
                        tp = time.perf_counter()
                        parallel.search(q, limit=10)
                        parallel_times.append((time.perf_counter() - tp) * 1000.0)

            stats = recovered.stats()
        finally:
            recovered.close()

    serial_sorted = sorted(serial_times)
    parallel_sorted = sorted(parallel_times)

    serial_summary = QueryLatencySummary(
        mode="serial",
        queries_run=len(serial_sorted),
        mean_ms=round(statistics.mean(serial_sorted), 3),
        p50_ms=round(_percentile(serial_sorted, 0.50), 3),
        p95_ms=round(_percentile(serial_sorted, 0.95), 3),
        p99_ms=round(_percentile(serial_sorted, 0.99), 3),
    )
    parallel_summary = QueryLatencySummary(
        mode=f"parallel({num_workers}w)",
        queries_run=len(parallel_sorted),
        mean_ms=round(statistics.mean(parallel_sorted), 3),
        p50_ms=round(_percentile(parallel_sorted, 0.50), 3),
        p95_ms=round(_percentile(parallel_sorted, 0.95), 3),
        p99_ms=round(_percentile(parallel_sorted, 0.99), 3),
    )

    return {
        "num_docs": num_docs,
        "vocabulary_size": stats["vocabulary_size"],
        "total_tokens": stats["total_tokens"],
        "ingest_ms": round(ingest_ms, 2),
        "ingest_docs_per_sec": round(num_docs / (ingest_ms / 1000.0), 1),
        "recovery_ms": round(recovery_ms, 2),
        "serial": serial_summary,
        "parallel": parallel_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SearchCore performance benchmark")
    parser.add_argument("--docs", type=int, default=2000, help="Number of documents to index")
    parser.add_argument("--iterations", type=int, default=20, help="Iterations over query suite")
    parser.add_argument("--workers", type=int, default=2, help="Parallel worker process count")
    args = parser.parse_args()

    report = run_benchmark(
        num_docs=args.docs,
        iterations=args.iterations,
        num_workers=args.workers,
    )
    print(f"Corpus: {report['num_docs']} docs | {report['total_tokens']} tokens | vocab={report['vocabulary_size']}")
    print(f"Ingest: {report['ingest_ms']} ms ({report['ingest_docs_per_sec']} docs/s)")
    print(f"Restart recovery: {report['recovery_ms']} ms")
    for key in ("serial", "parallel"):
        s = report[key]
        assert isinstance(s, QueryLatencySummary)
        print(
            f"{s.mode:14s} | n={s.queries_run:4d} | mean={s.mean_ms:6.3f} ms | "
            f"p50={s.p50_ms:6.3f} ms | p95={s.p95_ms:6.3f} ms | p99={s.p99_ms:6.3f} ms"
        )


if __name__ == "__main__":
    main()

