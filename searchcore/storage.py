"""SQLite persistence layer for SearchCore documents and inverted index postings."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_positions(positions: list[int]) -> str:
    return ",".join(str(p) for p in positions)


def _decode_positions(raw: str) -> list[int]:
    if not raw:
        return []
    return [int(part) for part in raw.split(",")]


@dataclass(frozen=True)
class DocumentRecord:
    """Stored document record returned from SQLite."""

    doc_id: int
    external_id: str | None
    title: str
    content: str
    doc_length: int
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class DocumentStore:
    """Transactional SQLite store for documents and positional postings."""

    def __init__(self, db_path: str | Path = "searchcore.db") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init_schema()

    def _configure_connection(self) -> None:
        if self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    external_id TEXT UNIQUE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    doc_length INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS postings (
                    term TEXT NOT NULL,
                    doc_id INTEGER NOT NULL,
                    tf INTEGER NOT NULL,
                    positions TEXT NOT NULL,
                    PRIMARY KEY (term, doc_id),
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_postings_doc_id
                    ON postings(doc_id);
                """
            )

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> DocumentRecord:
        return DocumentRecord(
            doc_id=int(row["id"]),
            external_id=row["external_id"],
            title=row["title"],
            content=row["content"],
            doc_length=int(row["doc_length"]),
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _upsert_one_in_tx(
        self,
        title: str,
        content: str,
        doc_length: int,
        positions_by_term: dict[str, list[int]],
        external_id: str | None,
        metadata: dict[str, Any] | None,
        now: str,
    ) -> tuple[DocumentRecord, list[str]]:
        meta_json = json.dumps(metadata or {}, sort_keys=True)
        old_terms: list[str] = []
        existing_id: int | None = None

        if external_id is not None:
            row = self._conn.execute(
                "SELECT id FROM documents WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if row is not None:
                existing_id = int(row["id"])

        if existing_id is not None:
            old_terms = [
                r["term"]
                for r in self._conn.execute(
                    "SELECT term FROM postings WHERE doc_id = ?",
                    (existing_id,),
                )
            ]
            self._conn.execute("DELETE FROM postings WHERE doc_id = ?", (existing_id,))
            self._conn.execute(
                """
                UPDATE documents
                SET title = ?, content = ?, doc_length = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, content, doc_length, meta_json, now, existing_id),
            )
            doc_id = existing_id
        else:
            cur = self._conn.execute(
                """
                INSERT INTO documents (
                    external_id, title, content, doc_length, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (external_id, title, content, doc_length, meta_json, now, now),
            )
            doc_id = int(cur.lastrowid)

        if positions_by_term:
            self._conn.executemany(
                "INSERT INTO postings (term, doc_id, tf, positions) VALUES (?, ?, ?, ?)",
                [
                    (term, doc_id, len(pos_list), _encode_positions(pos_list))
                    for term, pos_list in positions_by_term.items()
                ],
            )

        saved_row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        assert saved_row is not None
        return self._row_to_record(saved_row), old_terms

    def upsert_document(
        self,
        title: str,
        content: str,
        doc_length: int,
        positions_by_term: dict[str, list[int]],
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[DocumentRecord, list[str]]:
        """Insert or update a document (by external_id) and replace its postings atomically.

        Returns the saved DocumentRecord and the list of previously indexed terms (if updated).
        """
        now = _utc_now_iso()
        with self._conn:
            return self._upsert_one_in_tx(
                title=title,
                content=content,
                doc_length=doc_length,
                positions_by_term=positions_by_term,
                external_id=external_id,
                metadata=metadata,
                now=now,
            )

    def update_document_by_id(
        self,
        doc_id: int,
        title: str,
        content: str,
        doc_length: int,
        positions_by_term: dict[str, list[int]],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[DocumentRecord | None, list[str]]:
        """Update an existing document by integer doc_id and replace its postings atomically."""
        now = _utc_now_iso()
        meta_json = json.dumps(metadata or {}, sort_keys=True)

        with self._conn:
            existing = self._conn.execute(
                "SELECT id FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if existing is None:
                return None, []

            old_terms = [
                r["term"]
                for r in self._conn.execute(
                    "SELECT term FROM postings WHERE doc_id = ?",
                    (doc_id,),
                )
            ]
            self._conn.execute("DELETE FROM postings WHERE doc_id = ?", (doc_id,))
            self._conn.execute(
                """
                UPDATE documents
                SET title = ?, content = ?, doc_length = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, content, doc_length, meta_json, now, doc_id),
            )
            if positions_by_term:
                self._conn.executemany(
                    "INSERT INTO postings (term, doc_id, tf, positions) VALUES (?, ?, ?, ?)",
                    [
                        (term, doc_id, len(pos_list), _encode_positions(pos_list))
                        for term, pos_list in positions_by_term.items()
                    ],
                )
            saved_row = self._conn.execute(
                "SELECT * FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()

        assert saved_row is not None
        return self._row_to_record(saved_row), old_terms

    def batch_upsert_documents(
        self,
        items: list[tuple[str | None, str, str, int, dict[str, list[int]], dict[str, Any]]],
    ) -> list[tuple[DocumentRecord, list[str]]]:
        """Upsert multiple documents in a single SQLite transaction."""
        now = _utc_now_iso()
        results: list[tuple[DocumentRecord, list[str]]] = []

        with self._conn:
            for external_id, title, content, doc_length, positions_by_term, metadata in items:
                results.append(
                    self._upsert_one_in_tx(
                        title=title,
                        content=content,
                        doc_length=doc_length,
                        positions_by_term=positions_by_term,
                        external_id=external_id,
                        metadata=metadata,
                        now=now,
                    )
                )

        return results

    def delete_document(self, doc_id: int) -> list[str] | None:
        """Delete a document and its postings by doc_id. Returns removed terms, or None if missing."""
        with self._conn:
            row = self._conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row is None:
                return None
            old_terms = [
                r["term"]
                for r in self._conn.execute(
                    "SELECT term FROM postings WHERE doc_id = ?",
                    (doc_id,),
                )
            ]
            self._conn.execute("DELETE FROM postings WHERE doc_id = ?", (doc_id,))
            self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return old_terms

    def delete_by_external_id(self, external_id: str) -> tuple[int, list[str]] | None:
        """Delete a document by external_id. Returns (doc_id, removed_terms) or None."""
        row = self._conn.execute(
            "SELECT id FROM documents WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        if row is None:
            return None
        doc_id = int(row["id"])
        removed = self.delete_document(doc_id)
        if removed is None:
            return None
        return doc_id, removed

    def get_document(self, doc_id: int) -> DocumentRecord | None:
        """Fetch a single document by doc_id."""
        row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._row_to_record(row) if row is not None else None

    def get_document_by_external_id(self, external_id: str) -> DocumentRecord | None:
        """Fetch a single document by external_id."""
        row = self._conn.execute(
            "SELECT * FROM documents WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def get_documents_by_ids(self, doc_ids: list[int]) -> dict[int, DocumentRecord]:
        """Batch fetch documents by a list of doc_ids."""
        if not doc_ids:
            return {}
        placeholders = ",".join("?" for _ in doc_ids)
        rows = self._conn.execute(
            f"SELECT * FROM documents WHERE id IN ({placeholders})",
            tuple(doc_ids),
        ).fetchall()
        return {int(r["id"]): self._row_to_record(r) for r in rows}

    def list_documents(self, limit: int = 100, offset: int = 0) -> list[DocumentRecord]:
        """Return paginated documents ordered by doc_id."""
        rows = self._conn.execute(
            "SELECT * FROM documents ORDER BY id ASC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_documents(self) -> int:
        """Return total stored document count."""
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM documents").fetchone()
        return int(row["cnt"]) if row is not None else 0

    def load_index_snapshot(self) -> tuple[dict[int, int], dict[str, dict[int, list[int]]]]:
        """Load doc lengths and positional postings from SQLite for restart recovery."""
        doc_lengths: dict[int, int] = {}
        for row in self._conn.execute("SELECT id, doc_length FROM documents"):
            doc_lengths[int(row["id"])] = int(row["doc_length"])

        postings: dict[str, dict[int, list[int]]] = {}
        for row in self._conn.execute("SELECT term, doc_id, positions FROM postings"):
            term = row["term"]
            doc_id = int(row["doc_id"])
            pos_list = _decode_positions(row["positions"])
            term_map = postings.setdefault(term, {})
            term_map[doc_id] = pos_list

        return doc_lengths, postings

    def replace_all_postings(
        self,
        doc_lengths: dict[int, int],
        postings_by_doc: dict[int, dict[str, list[int]]],
    ) -> None:
        """Rewrite postings table and doc_length values in a single transaction (for index rebuild)."""
        with self._conn:
            self._conn.execute("DELETE FROM postings")
            for doc_id, length in doc_lengths.items():
                self._conn.execute(
                    "UPDATE documents SET doc_length = ? WHERE id = ?",
                    (length, doc_id),
                )
            rows = [
                (term, doc_id, len(pos_list), _encode_positions(pos_list))
                for doc_id, term_map in postings_by_doc.items()
                for term, pos_list in term_map.items()
            ]
            if rows:
                self._conn.executemany(
                    "INSERT INTO postings (term, doc_id, tf, positions) VALUES (?, ?, ?, ?)",
                    rows,
                )

    def iter_all_documents(self) -> list[DocumentRecord]:
        """Return all stored documents (used for full index rebuild or verification)."""
        rows = self._conn.execute("SELECT * FROM documents ORDER BY id ASC").fetchall()
        return [self._row_to_record(r) for r in rows]
