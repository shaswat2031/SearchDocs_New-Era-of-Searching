"""In-memory positional inverted index and persistent SearchEngine coordinator."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from searchcore.bm25 import score_bm25
from searchcore.query_parser import (
    AndNode,
    NotNode,
    OrNode,
    PhraseNode,
    QueryNode,
    TermNode,
    collect_terms,
    parse_query,
)
from searchcore.storage import DocumentRecord, DocumentStore
from searchcore.tokenizer import tokenize_document


@dataclass(frozen=True)
class SearchHit:
    """Single ranked search result."""

    doc_id: int
    external_id: str | None
    title: str
    score: float
    snippet: str
    match_count: int = 0
    snippets: list[str] = field(default_factory=list)
    content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResponse:
    """Structured response returned by SearchEngine.search."""

    query: str
    total_hits: int
    took_ms: float
    hits: list[SearchHit]


def build_all_snippets(
    content: str,
    query_terms: set[str],
    title: str = "",
    window_chars: int = 65,
    max_fragments: int = 50,
) -> tuple[list[str], int]:
    """Return merged context excerpts for every occurrence of query_terms and total match count."""
    clean_content = " ".join(content.split())
    clean_title = " ".join(title.split())

    if not query_terms:
        fallback = clean_content[:220].rstrip() + ("..." if len(clean_content) > 220 else "")
        return ([fallback] if fallback else []), 0

    escaped_terms = sorted((re.escape(t) for t in query_terms if t), key=len, reverse=True)
    if not escaped_terms:
        return [], 0
    pattern = re.compile(rf"\b(?:{'|'.join(escaped_terms)})\b", re.IGNORECASE)

    title_matches = list(pattern.finditer(clean_title)) if clean_title else []
    content_matches = list(pattern.finditer(clean_content)) if clean_content else []
    total_matches = len(title_matches) + len(content_matches)

    if not content_matches:
        if not clean_content:
            return [], total_matches
        fallback = clean_content[:217].rstrip() + "..." if len(clean_content) > 220 else clean_content
        return [fallback], total_matches

    windows: list[list[int]] = []
    for m in content_matches:
        start = max(0, m.start() - window_chars)
        end = min(len(clean_content), m.end() + window_chars)
        if windows and start <= windows[-1][1] + 20:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])

    fragments: list[str] = []
    for start, end in windows[:max_fragments]:
        # Snap to nearest word boundary so words are not split mid-token.
        if start > 0:
            space_after = clean_content.find(" ", start)
            if space_after != -1 and space_after - start < 15:
                start = space_after + 1
        if end < len(clean_content):
            space_before = clean_content.rfind(" ", start, end)
            if space_before != -1 and end - space_before < 15:
                end = space_before

        excerpt = clean_content[start:end].strip()
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(clean_content):
            excerpt = excerpt.rstrip() + "..."
        fragments.append(excerpt)

    return fragments, total_matches


def build_snippet(content: str, query_terms: set[str], max_length: int = 220) -> str:
    """Return a concise excerpt centered near the first matched query term."""
    fragments, _ = build_all_snippets(
        content=content,
        query_terms=query_terms,
        window_chars=max(40, max_length // 3),
        max_fragments=1,
    )
    if not fragments:
        return ""
    first = fragments[0]
    if len(first) <= max_length:
        return first
    return first[: max_length - 3].rstrip() + "..."


class InvertedIndex:
    """Positional inverted index supporting boolean AST evaluation, phrases, and BM25 ranking."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.postings: dict[str, dict[int, list[int]]] = {}
        self.doc_lengths: dict[int, int] = {}
        self.total_tokens: int = 0

    @property
    def total_docs(self) -> int:
        return len(self.doc_lengths)

    @property
    def avg_doc_length(self) -> float:
        if not self.doc_lengths:
            return 0.0
        return self.total_tokens / len(self.doc_lengths)

    @property
    def vocabulary_size(self) -> int:
        return len(self.postings)

    def load_snapshot(
        self,
        doc_lengths: dict[int, int],
        postings: dict[str, dict[int, list[int]]],
    ) -> None:
        """Replace in-memory index contents from a persisted snapshot."""
        self.doc_lengths = dict(doc_lengths)
        self.postings = postings
        self.total_tokens = sum(doc_lengths.values())

    def remove_document(self, doc_id: int, known_terms: list[str] | None = None) -> None:
        """Remove a document and all its postings from the inverted index."""
        old_length = self.doc_lengths.pop(doc_id, None)
        if old_length is not None:
            self.total_tokens -= old_length

        if known_terms is not None:
            terms_to_check = known_terms
        else:
            terms_to_check = [term for term, docs in self.postings.items() if doc_id in docs]

        for term in terms_to_check:
            term_docs = self.postings.get(term)
            if term_docs is None:
                continue
            term_docs.pop(doc_id, None)
            if not term_docs:
                del self.postings[term]

    def index_document(
        self,
        doc_id: int,
        doc_length: int,
        positions_by_term: dict[str, list[int]],
        old_terms: list[str] | None = None,
    ) -> None:
        """Insert or replace a document's postings in the inverted index."""
        if doc_id in self.doc_lengths:
            self.remove_document(doc_id, known_terms=old_terms)

        self.doc_lengths[doc_id] = doc_length
        self.total_tokens += doc_length

        for term, positions in positions_by_term.items():
            term_docs = self.postings.setdefault(term, {})
            term_docs[doc_id] = positions

    def lookup_term(self, term: str) -> dict[int, list[int]]:
        """Return the posting map {doc_id: positions} for a normalized term."""
        return self.postings.get(term, {})

    def doc_freq(self, term: str) -> int:
        """Return document frequency for a term."""
        return len(self.postings.get(term, {}))

    def match_phrase_counts(self, terms: tuple[str, ...]) -> dict[int, int]:
        """Find documents containing the exact sequence of terms and count occurrences per doc."""
        if not terms:
            return {}
        if len(terms) == 1:
            return {
                doc_id: len(pos_list)
                for doc_id, pos_list in self.postings.get(terms[0], {}).items()
            }

        term_postings = [self.postings.get(term) for term in terms]
        if any(p is None or len(p) == 0 for p in term_postings):
            return {}

        # Intersect starting from the rarest term to minimize candidate checks.
        ordered = sorted(range(len(terms)), key=lambda i: len(term_postings[i]))  # type: ignore[arg-type]
        candidate_docs = set(term_postings[ordered[0]].keys())  # type: ignore[union-attr]
        for idx in ordered[1:]:
            candidate_docs &= term_postings[idx].keys()  # type: ignore[union-attr]
            if not candidate_docs:
                return {}

        matches: dict[int, int] = {}
        first_postings = term_postings[0]
        assert first_postings is not None

        for doc_id in candidate_docs:
            start_positions = set(first_postings[doc_id])
            for offset in range(1, len(terms)):
                next_postings = term_postings[offset]
                assert next_postings is not None
                next_positions = set(next_postings[doc_id])
                start_positions = {p for p in start_positions if (p + offset) in next_positions}
                if not start_positions:
                    break
            if start_positions:
                matches[doc_id] = len(start_positions)

        return matches

    def evaluate_ast(
        self,
        node: QueryNode,
        global_total_docs: int | None = None,
        global_avg_dl: float | None = None,
        global_term_dfs: dict[str, int] | None = None,
        global_phrase_dfs: dict[tuple[str, ...], int] | None = None,
    ) -> dict[int, float]:
        """Evaluate a parsed query AST and return {doc_id: bm25_score}."""
        n_docs = global_total_docs if global_total_docs is not None else self.total_docs
        avg_dl = global_avg_dl if global_avg_dl is not None else self.avg_doc_length

        if n_docs == 0 or not self.doc_lengths:
            return {}

        if isinstance(node, TermNode):
            postings = self.postings.get(node.term)
            if not postings:
                return {}
            df = (
                global_term_dfs.get(node.term, len(postings))
                if global_term_dfs is not None
                else len(postings)
            )
            return {
                doc_id: score_bm25(
                    tf=len(positions),
                    doc_length=self.doc_lengths[doc_id],
                    avg_doc_length=avg_dl,
                    total_docs=n_docs,
                    doc_freq=df,
                    k1=self.k1,
                    b=self.b,
                )
                for doc_id, positions in postings.items()
            }

        if isinstance(node, PhraseNode):
            phrase_counts = self.match_phrase_counts(node.terms)
            if not phrase_counts:
                return {}
            df = (
                global_phrase_dfs.get(node.terms, len(phrase_counts))
                if global_phrase_dfs is not None
                else len(phrase_counts)
            )
            return {
                doc_id: score_bm25(
                    tf=pf,
                    doc_length=self.doc_lengths[doc_id],
                    avg_doc_length=avg_dl,
                    total_docs=n_docs,
                    doc_freq=df,
                    k1=self.k1,
                    b=self.b,
                )
                for doc_id, pf in phrase_counts.items()
            }

        if isinstance(node, NotNode):
            excluded = self.evaluate_ast(
                node.operand,
                global_total_docs=n_docs,
                global_avg_dl=avg_dl,
                global_term_dfs=global_term_dfs,
                global_phrase_dfs=global_phrase_dfs,
            )
            return {doc_id: 1.0 for doc_id in self.doc_lengths if doc_id not in excluded}

        if isinstance(node, AndNode):
            # Short-circuit A AND NOT B without scanning the full corpus.
            if isinstance(node.right, NotNode):
                left_scores = self.evaluate_ast(
                    node.left, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
                )
                if not left_scores:
                    return {}
                excluded = self.evaluate_ast(
                    node.right.operand, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
                )
                return {d: s for d, s in left_scores.items() if d not in excluded}

            if isinstance(node.left, NotNode):
                right_scores = self.evaluate_ast(
                    node.right, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
                )
                if not right_scores:
                    return {}
                excluded = self.evaluate_ast(
                    node.left.operand, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
                )
                return {d: s for d, s in right_scores.items() if d not in excluded}

            left_scores = self.evaluate_ast(
                node.left, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
            )
            if not left_scores:
                return {}
            right_scores = self.evaluate_ast(
                node.right, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
            )
            if not right_scores:
                return {}
            return {
                doc_id: left_scores[doc_id] + right_scores[doc_id]
                for doc_id in left_scores.keys() & right_scores.keys()
            }

        if isinstance(node, OrNode):
            left_scores = self.evaluate_ast(
                node.left, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
            )
            right_scores = self.evaluate_ast(
                node.right, n_docs, avg_dl, global_term_dfs, global_phrase_dfs
            )
            merged = dict(left_scores)
            for doc_id, score in right_scores.items():
                merged[doc_id] = merged.get(doc_id, 0.0) + score
            return merged

        return {}

    def rank_ast(
        self,
        node: QueryNode,
        global_total_docs: int | None = None,
        global_avg_dl: float | None = None,
        global_term_dfs: dict[str, int] | None = None,
        global_phrase_dfs: dict[tuple[str, ...], int] | None = None,
    ) -> list[tuple[int, float]]:
        """Evaluate AST and return all matches sorted by (-score, doc_id)."""
        scores = self.evaluate_ast(
            node,
            global_total_docs=global_total_docs,
            global_avg_dl=global_avg_dl,
            global_term_dfs=global_term_dfs,
            global_phrase_dfs=global_phrase_dfs,
        )
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class SearchEngine:
    """Thread-safe document search engine backed by SQLite storage and an in-memory inverted index."""

    def __init__(
        self,
        db_path: str | Path = "searchcore.db",
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.store = DocumentStore(db_path=db_path)
        self.index = InvertedIndex(k1=k1, b=b)
        self._lock = threading.RLock()
        self.version: int = 0
        self.recover()

    def close(self) -> None:
        """Close the backing SQLite store."""
        with self._lock:
            self.store.close()

    def recover(self) -> None:
        """Load documents and postings from SQLite to restore index state after restart."""
        with self._lock:
            doc_lengths, postings = self.store.load_index_snapshot()
            self.index.load_snapshot(doc_lengths, postings)
            self.version += 1

    def rebuild_index(self) -> dict[str, int]:
        """Re-tokenize all documents in SQLite and rewrite the persisted inverted index."""
        with self._lock:
            docs = self.store.iter_all_documents()
            doc_lengths: dict[int, int] = {}
            postings_by_doc: dict[int, dict[str, list[int]]] = {}
            for doc in docs:
                positions_by_term, length = tokenize_document(doc.title, doc.content)
                doc_lengths[doc.doc_id] = length
                postings_by_doc[doc.doc_id] = positions_by_term

            self.store.replace_all_postings(doc_lengths, postings_by_doc)
            self.recover()
            return {
                "documents_reindexed": len(docs),
                "vocabulary_size": self.index.vocabulary_size,
                "total_tokens": self.index.total_tokens,
            }

    def add_document(
        self,
        title: str,
        content: str,
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentRecord:
        """Index and persist a new document (or update an existing one with matching external_id)."""
        positions_by_term, doc_length = tokenize_document(title, content)
        with self._lock:
            record, old_terms = self.store.upsert_document(
                title=title,
                content=content,
                doc_length=doc_length,
                positions_by_term=positions_by_term,
                external_id=external_id,
                metadata=metadata,
            )
            self.index.index_document(
                doc_id=record.doc_id,
                doc_length=doc_length,
                positions_by_term=positions_by_term,
                old_terms=old_terms,
            )
            self.version += 1
            return record

    def add_documents_batch(
        self,
        documents: list[dict[str, Any]],
    ) -> list[DocumentRecord]:
        """Index and persist multiple documents inside a single SQLite transaction."""
        prepared: list[tuple[str | None, str, str, int, dict[str, list[int]], dict[str, Any]]] = []
        tokenized_payloads: list[tuple[int, dict[str, list[int]]]] = []

        for doc in documents:
            title = str(doc.get("title", ""))
            content = str(doc.get("content", ""))
            external_id = doc.get("external_id")
            metadata = doc.get("metadata") or {}
            positions_by_term, doc_length = tokenize_document(title, content)
            prepared.append((external_id, title, content, doc_length, positions_by_term, metadata))
            tokenized_payloads.append((doc_length, positions_by_term))

        with self._lock:
            saved = self.store.batch_upsert_documents(prepared)
            for (record, old_terms), (doc_length, positions_by_term) in zip(
                saved, tokenized_payloads
            ):
                self.index.index_document(
                    doc_id=record.doc_id,
                    doc_length=doc_length,
                    positions_by_term=positions_by_term,
                    old_terms=old_terms,
                )
            self.version += 1
            return [record for record, _ in saved]

    def update_document(
        self,
        doc_id: int,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentRecord | None:
        """Update an existing document by doc_id and refresh its inverted index postings."""
        positions_by_term, doc_length = tokenize_document(title, content)
        with self._lock:
            record, old_terms = self.store.update_document_by_id(
                doc_id=doc_id,
                title=title,
                content=content,
                doc_length=doc_length,
                positions_by_term=positions_by_term,
                metadata=metadata,
            )
            if record is None:
                return None
            self.index.index_document(
                doc_id=record.doc_id,
                doc_length=doc_length,
                positions_by_term=positions_by_term,
                old_terms=old_terms,
            )
            self.version += 1
            return record

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document by doc_id from SQLite and the inverted index."""
        with self._lock:
            old_terms = self.store.delete_document(doc_id)
            if old_terms is None:
                return False
            self.index.remove_document(doc_id, known_terms=old_terms)
            self.version += 1
            return True

    def delete_by_external_id(self, external_id: str) -> bool:
        """Delete a document by external_id from SQLite and the inverted index."""
        with self._lock:
            result = self.store.delete_by_external_id(external_id)
            if result is None:
                return False
            doc_id, old_terms = result
            self.index.remove_document(doc_id, known_terms=old_terms)
            self.version += 1
            return True

    def get_document(self, doc_id: int) -> DocumentRecord | None:
        """Fetch a stored document by doc_id."""
        with self._lock:
            return self.store.get_document(doc_id)

    def get_document_by_external_id(self, external_id: str) -> DocumentRecord | None:
        """Fetch a stored document by external_id."""
        with self._lock:
            return self.store.get_document_by_external_id(external_id)

    def list_documents(self, limit: int = 100, offset: int = 0) -> list[DocumentRecord]:
        """List stored documents with pagination."""
        with self._lock:
            return self.store.list_documents(limit=limit, offset=offset)

    def _hydrate_hits(
        self,
        ranked_pairs: list[tuple[int, float]],
        query_terms: set[str],
        limit: int,
        offset: int,
        include_content: bool,
    ) -> list[SearchHit]:
        page = ranked_pairs[offset : offset + limit]
        if not page:
            return []
        doc_ids = [doc_id for doc_id, _ in page]
        docs_by_id = self.store.get_documents_by_ids(doc_ids)

        hits: list[SearchHit] = []
        for doc_id, score in page:
            record = docs_by_id.get(doc_id)
            if record is None:
                continue
            fragments, match_count = build_all_snippets(
                content=record.content,
                query_terms=query_terms,
                title=record.title,
            )
            primary_snippet = fragments[0] if fragments else ""
            hits.append(
                SearchHit(
                    doc_id=record.doc_id,
                    external_id=record.external_id,
                    title=record.title,
                    score=round(score, 6),
                    snippet=primary_snippet,
                    match_count=match_count,
                    snippets=fragments,
                    content=record.content if include_content else None,
                    metadata=record.metadata,
                )
            )
        return hits

    def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        default_operator: Literal["AND", "OR"] = "AND",
        include_content: bool = True,
    ) -> SearchResponse:
        """Parse and execute a search query with BM25 ranking."""
        t0 = time.perf_counter()
        ast = parse_query(query, default_operator=default_operator)
        terms = collect_terms(ast)

        with self._lock:
            ranked = self.index.rank_ast(ast)
            hits = self._hydrate_hits(
                ranked_pairs=ranked,
                query_terms=terms,
                limit=limit,
                offset=offset,
                include_content=include_content,
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return SearchResponse(
            query=query,
            total_hits=len(ranked),
            took_ms=round(elapsed_ms, 3),
            hits=hits,
        )

    def stats(self) -> dict[str, Any]:
        """Return corpus and index statistics."""
        with self._lock:
            return {
                "db_path": self.store.db_path,
                "total_documents": self.index.total_docs,
                "total_tokens": self.index.total_tokens,
                "avg_doc_length": round(self.index.avg_doc_length, 3),
                "vocabulary_size": self.index.vocabulary_size,
                "k1": self.index.k1,
                "b": self.index.b,
                "index_version": self.version,
            }

