"""Multi-process parallel search engine across sharded inverted indexes."""

from __future__ import annotations

import multiprocessing
import os
import time
from multiprocessing.connection import Connection
from typing import Any, Literal

from searchcore.index import InvertedIndex, SearchEngine, SearchResponse
from searchcore.query_parser import QueryNode, collect_phrases, collect_terms, parse_query


def _shard_worker_loop(
    conn: Connection,
    k1: float,
    b: float,
) -> None:
    """Worker process event loop holding one disjoint inverted-index shard."""
    shard = InvertedIndex(k1=k1, b=b)

    try:
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                break

            cmd = msg[0]
            if cmd == "SHUTDOWN":
                conn.send(("OK",))
                break

            if cmd == "LOAD_SHARD":
                _, doc_lengths, postings = msg
                shard.load_snapshot(doc_lengths, postings)
                conn.send(("OK", shard.total_docs))

            elif cmd == "COUNT_PHRASES":
                _, phrases = msg
                counts = {phrase: len(shard.match_phrase_counts(phrase)) for phrase in phrases}
                conn.send(("PHRASE_COUNTS", counts))

            elif cmd == "EVAL_AST":
                _, ast, total_docs, avg_dl, term_dfs, phrase_dfs, top_n = msg
                ranked = shard.rank_ast(
                    ast,
                    global_total_docs=total_docs,
                    global_avg_dl=avg_dl,
                    global_term_dfs=term_dfs,
                    global_phrase_dfs=phrase_dfs,
                )
                total_shard_hits = len(ranked)
                partial = ranked[:top_n] if top_n is not None else ranked
                conn.send(("RESULTS", total_shard_hits, partial))
    finally:
        conn.close()


class ParallelSearchEngine:
    """Distributes search queries across separate OS worker processes over document shards.

    Each worker holds a disjoint shard (doc_id % num_workers) of the inverted index,
    while BM25 scoring uses global corpus statistics (N, avgdl, global df) so rankings
    are identical to single-process SearchEngine.search().
    """

    def __init__(
        self,
        engine: SearchEngine,
        num_workers: int | None = None,
    ) -> None:
        self.engine = engine
        default_workers = max(2, min(os.cpu_count() or 2, 4))
        self.num_workers = max(1, num_workers if num_workers is not None else default_workers)
        self._ctx = multiprocessing.get_context("spawn")
        self._processes: list[multiprocessing.process.BaseProcess] = []
        self._conns: list[Connection] = []
        self._synced_version: int = -1
        self._started: bool = False

    def __enter__(self) -> ParallelSearchEngine:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()

    @property
    def is_running(self) -> bool:
        return self._started and all(p.is_alive() for p in self._processes)

    @property
    def worker_pids(self) -> list[int]:
        """Return OS process IDs of active search worker processes."""
        return [p.pid for p in self._processes if p.pid is not None]

    def start(self) -> None:
        """Spawn worker processes and synchronize the current index shards."""
        if self._started:
            return

        k1 = self.engine.index.k1
        b = self.engine.index.b

        for idx in range(self.num_workers):
            parent_conn, child_conn = self._ctx.Pipe()
            proc = self._ctx.Process(
                target=_shard_worker_loop,
                args=(child_conn, k1, b),
                name=f"searchcore-worker-{idx}",
                daemon=True,
            )
            proc.start()
            child_conn.close()
            self._processes.append(proc)
            self._conns.append(parent_conn)

        self._started = True
        self.sync()

    def shutdown(self) -> None:
        """Gracefully terminate all worker processes."""
        if not self._started:
            return
        for conn in self._conns:
            try:
                conn.send(("SHUTDOWN",))
            except (BrokenPipeError, EOFError, OSError):
                pass
        for conn in self._conns:
            try:
                conn.recv()
            except (BrokenPipeError, EOFError, OSError):
                pass
            finally:
                conn.close()
        for proc in self._processes:
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1.0)
        self._processes.clear()
        self._conns.clear()
        self._synced_version = -1
        self._started = False

    def sync(self) -> None:
        """Partition the coordinator's inverted index across worker shards if stale."""
        if not self._started:
            self.start()
            return

        with self.engine._lock:
            current_version = self.engine.version
            if current_version == self._synced_version:
                return

            w = self.num_workers
            shard_doc_lengths: list[dict[int, int]] = [{} for _ in range(w)]
            shard_postings: list[dict[str, dict[int, list[int]]]] = [{} for _ in range(w)]

            for doc_id, length in self.engine.index.doc_lengths.items():
                shard_doc_lengths[doc_id % w][doc_id] = length

            for term, doc_map in self.engine.index.postings.items():
                for doc_id, positions in doc_map.items():
                    s_idx = doc_id % w
                    term_dict = shard_postings[s_idx].setdefault(term, {})
                    term_dict[doc_id] = positions

            self._synced_version = current_version

        for conn, d_lens, posts in zip(self._conns, shard_doc_lengths, shard_postings):
            conn.send(("LOAD_SHARD", d_lens, posts))
        for conn in self._conns:
            conn.recv()

    def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        default_operator: Literal["AND", "OR"] = "AND",
        include_content: bool = True,
    ) -> SearchResponse:
        """Execute a search query in parallel across worker processes and merge top-k hits."""
        if not self._started:
            self.start()
        elif self._synced_version != self.engine.version:
            self.sync()

        t0 = time.perf_counter()
        ast: QueryNode = parse_query(query, default_operator=default_operator)
        terms = collect_terms(ast)
        phrases = collect_phrases(ast)

        with self.engine._lock:
            if self._synced_version != self.engine.version:
                self.sync()
            total_docs = self.engine.index.total_docs
            avg_dl = self.engine.index.avg_doc_length
            term_dfs = {term: self.engine.index.doc_freq(term) for term in terms}

        phrase_dfs: dict[tuple[str, ...], int] | None = None
        if phrases:
            phrase_list = list(phrases)
            for conn in self._conns:
                conn.send(("COUNT_PHRASES", phrase_list))
            phrase_dfs = {phrase: 0 for phrase in phrase_list}
            for conn in self._conns:
                _, counts = conn.recv()
                for phrase, cnt in counts.items():
                    phrase_dfs[phrase] += cnt

        top_n = offset + limit if limit >= 0 else None
        for conn in self._conns:
            conn.send(("EVAL_AST", ast, total_docs, avg_dl, term_dfs, phrase_dfs, top_n))

        total_hits = 0
        merged_pairs: list[tuple[int, float]] = []
        for conn in self._conns:
            _, shard_hits, partial = conn.recv()
            total_hits += shard_hits
            merged_pairs.extend(partial)

        merged_pairs.sort(key=lambda item: (-item[1], item[0]))

        with self.engine._lock:
            hits = self.engine._hydrate_hits(
                ranked_pairs=merged_pairs,
                query_terms=terms,
                limit=limit,
                offset=offset,
                include_content=include_content,
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return SearchResponse(
            query=query,
            total_hits=total_hits,
            took_ms=round(elapsed_ms, 3),
            hits=hits,
        )

