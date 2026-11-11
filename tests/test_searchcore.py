"""End-to-end tests for SearchCore indexing, ranking, persistence, parallel search, and API."""

from __future__ import annotations

from pathlib import Path

import pytest

from searchcore import (
    ParallelSearchEngine,
    QuerySyntaxError,
    SearchEngine,
    compute_idf,
    import_directory,
    import_uploaded_files,
    parse_query,
    score_bm25,
    tokenize,
    tokenize_document,
)
from searchcore.api import _execute_search, create_app


def test_tokenizer_normalization_and_boundary_gap() -> None:
    # Fullwidth compatibility characters normalize under NFKC before lowercasing.
    assert tokenize("\uff26\uff41\uff53\uff54\uff21\uff30\uff29 BM25_v2!") == [
        "fastapi",
        "bm25",
        "v2",
    ]
    positions, total = tokenize_document("FastAPI Search", "Engine core")
    # "fastapi": [0], "search": [1], gap at 2, "engine": [3], "core": [4]
    assert positions["fastapi"] == [0]
    assert positions["search"] == [1]
    assert positions["engine"] == [3]
    assert positions["core"] == [4]
    assert total == 4


def test_bm25_non_negative_idf_and_monotonic_tf() -> None:
    assert compute_idf(total_docs=10, doc_freq=10) > 0.0
    assert compute_idf(total_docs=0, doc_freq=0) == 0.0

    low_tf = score_bm25(tf=1, doc_length=20, avg_doc_length=20.0, total_docs=10, doc_freq=2)
    high_tf = score_bm25(tf=4, doc_length=20, avg_doc_length=20.0, total_docs=10, doc_freq=2)
    assert high_tf > low_tf > 0.0


def test_query_parser_boolean_phrase_and_errors() -> None:
    ast = parse_query('("inverted index" OR sqlite) AND NOT draft')
    assert ast is not None

    with pytest.raises(QuerySyntaxError):
        parse_query("")
    with pytest.raises(QuerySyntaxError):
        parse_query('"unclosed phrase')
    with pytest.raises(QuerySyntaxError):
        parse_query("(python AND sqlite")


def test_engine_crud_phrase_boundary_and_restart_recovery(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = SearchEngine(db_path=db_path)
    try:
        doc1 = engine.add_document(
            title="Python Search",
            content="Engine internals with inverted index and BM25 ranking.",
            external_id="doc-1",
            metadata={"tag": "core"},
        )
        engine.add_document(
            title="SQLite WAL",
            content="Write ahead logging keeps inverted index durable across restarts.",
            external_id="doc-2",
        )

        # Phrase must NOT cross the title -> content boundary gap.
        boundary_hits = engine.search('"search engine"')
        assert boundary_hits.total_hits == 0

        # Exact phrase inside content matches both documents.
        phrase_hits = engine.search('"inverted index"')
        assert phrase_hits.total_hits == 2

        # Upsert via external_id replaces previous content cleanly.
        updated = engine.add_document(
            title="Python Search Updated",
            content="BM25 ranking only.",
            external_id="doc-1",
        )
        assert updated.doc_id == doc1.doc_id
        assert engine.search('"inverted index"').total_hits == 1
    finally:
        engine.close()

    # Reopen from SQLite and verify snapshot recovery + rebuild_index.
    recovered = SearchEngine(db_path=db_path)
    try:
        assert recovered.index.total_docs == 2
        assert recovered.search("bm25").total_hits == 1
        rebuilt = recovered.rebuild_index()
        assert rebuilt["documents_reindexed"] == 2
    finally:
        recovered.close()


def test_parallel_search_matches_serial_scores(tmp_path: Path) -> None:
    engine = SearchEngine(db_path=tmp_path / "parallel.db")
    try:
        docs = [
            {"external_id": f"d-{i}", "title": f"Note {i}", "content": content}
            for i, content in enumerate(
                [
                    "inverted index with bm25 scoring in python",
                    "sqlite wal storage and restart recovery",
                    "inverted index phrase matching across shards",
                    "fastapi service with inverted index and bm25",
                    "draft notes unrelated to search",
                ]
            )
        ]
        engine.add_documents_batch(docs)

        queries = [
            "bm25",
            '"inverted index"',
            '("inverted index" OR sqlite) AND NOT draft',
            "python OR fastapi",
        ]
        with ParallelSearchEngine(engine, num_workers=2) as parallel:
            for q in queries:
                serial_resp = engine.search(q, limit=10)
                parallel_resp = parallel.search(q, limit=10)
                assert parallel_resp.total_hits == serial_resp.total_hits
                assert [
                    (h.doc_id, h.score) for h in parallel_resp.hits
                ] == [
                    (h.doc_id, h.score) for h in serial_resp.hits
                ]
    finally:
        engine.close()


def test_importer_and_api_wiring(tmp_path: Path) -> None:
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    (sample_dir / "guide.md").write_text(
        "# BM25 Guide\n\nOkapi BM25 ranks documents using term frequency.",
        encoding="utf-8",
    )

    engine = SearchEngine(db_path=tmp_path / "import.db")
    try:
        imported = import_directory(engine, sample_dir)
        assert len(imported) == 1
        assert imported[0].title == "BM25 Guide"

        uploaded = import_uploaded_files(
            engine,
            [("notes.txt", b"Parallel search over SQLite shards.")],
        )
        assert len(uploaded) == 1

        app = create_app(db_path=tmp_path / "api.db")
        app.state.engine = engine
        app.state.parallel_engine = None
        app.state.num_workers = None

        route_paths = {getattr(route, "path", None) for route in app.routes}
        assert {"/health", "/stats", "/documents", "/documents/upload", "/search"}.issubset(
            route_paths
        )

        res = _execute_search(
            app=app,
            q="bm25 AND frequency",
            limit=10,
            offset=0,
            operator="AND",
            include_content=True,
            parallel=False,
        )
        assert res.mode == "serial"
        assert res.total_hits == 1
        assert res.hits[0].title == "BM25 Guide"
    finally:
        engine.close()
