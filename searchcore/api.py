"""FastAPI HTTP API for SearchCore — Document Search Engine."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from searchcore.importer import import_directory, import_uploaded_files
from searchcore.index import SearchEngine, SearchResponse
from searchcore.parallel import ParallelSearchEngine
from searchcore.query_parser import QuerySyntaxError
from searchcore.storage import DocumentRecord


class DocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(...)
    external_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(...)
    metadata: dict[str, Any] | None = Field(default=None)


class BatchDocumentsRequest(BaseModel):
    documents: list[DocumentCreateRequest] = Field(..., min_length=1)


class ImportDirectoryRequest(BaseModel):
    directory: str = Field(..., min_length=1)
    extensions: list[str] = Field(default_factory=lambda: [".txt", ".md", ".pdf", ".docx"])
    recursive: bool = True


class DocumentResponse(BaseModel):
    doc_id: int
    external_id: str | None
    title: str
    content: str
    doc_length: int
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, rec: DocumentRecord) -> DocumentResponse:
        return cls(
            doc_id=rec.doc_id,
            external_id=rec.external_id,
            title=rec.title,
            content=rec.content,
            doc_length=rec.doc_length,
            metadata=rec.metadata,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
        )


class SearchHitResponse(BaseModel):
    doc_id: int
    external_id: str | None
    title: str
    score: float
    snippet: str
    match_count: int = 0
    snippets: list[str] = Field(default_factory=list)
    content: str | None = None
    metadata: dict[str, Any]


class SearchApiResponse(BaseModel):
    query: str
    total_hits: int
    took_ms: float
    mode: Literal["serial", "parallel"]
    hits: list[SearchHitResponse]

    @classmethod
    def from_search_response(
        cls,
        resp: SearchResponse,
        mode: Literal["serial", "parallel"],
    ) -> SearchApiResponse:
        return cls(
            query=resp.query,
            total_hits=resp.total_hits,
            took_ms=resp.took_ms,
            mode=mode,
            hits=[
                SearchHitResponse(
                    doc_id=h.doc_id,
                    external_id=h.external_id,
                    title=h.title,
                    score=h.score,
                    snippet=h.snippet,
                    match_count=h.match_count,
                    snippets=h.snippets,
                    content=h.content,
                    metadata=h.metadata,
                )
                for h in resp.hits
            ],
        )


class SearchQueryRequest(BaseModel):
    q: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    operator: Literal["AND", "OR"] = "AND"
    include_content: bool = True
    parallel: bool = False


def _execute_search(
    app: FastAPI,
    q: str,
    limit: int,
    offset: int,
    operator: Literal["AND", "OR"],
    include_content: bool,
    parallel: bool,
) -> SearchApiResponse:
    engine: SearchEngine = app.state.engine
    try:
        if parallel:
            p_engine: ParallelSearchEngine | None = app.state.parallel_engine
            if p_engine is None:
                p_engine = ParallelSearchEngine(
                    engine=engine,
                    num_workers=app.state.num_workers,
                )
                p_engine.start()
                app.state.parallel_engine = p_engine
            resp = p_engine.search(
                query=q,
                limit=limit,
                offset=offset,
                default_operator=operator,
                include_content=include_content,
            )
            return SearchApiResponse.from_search_response(resp, mode="parallel")

        resp = engine.search(
            query=q,
            limit=limit,
            offset=offset,
            default_operator=operator,
            include_content=include_content,
        )
        return SearchApiResponse.from_search_response(resp, mode="serial")
    except QuerySyntaxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def create_app(
    db_path: str | Path | None = None,
    enable_parallel: bool = False,
    num_workers: int | None = None,
) -> FastAPI:
    """Create and configure a FastAPI application backed by SearchEngine."""
    resolved_db = str(db_path or os.environ.get("SEARCHCORE_DB", "searchcore.db"))

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        engine = SearchEngine(db_path=resolved_db)
        app_instance.state.engine = engine
        app_instance.state.num_workers = num_workers
        app_instance.state.parallel_engine = None
        if enable_parallel:
            p_engine = ParallelSearchEngine(engine=engine, num_workers=num_workers)
            p_engine.start()
            app_instance.state.parallel_engine = p_engine
        try:
            yield
        finally:
            if app_instance.state.parallel_engine is not None:
                app_instance.state.parallel_engine.shutdown()
                app_instance.state.parallel_engine = None
            engine.close()

    app = FastAPI(
        title="SearchCore — Document Search Engine",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fallback_ui_path = Path(__file__).resolve().parent / "static" / "index.html"
    next_out_dir = Path(__file__).resolve().parent.parent / "frontend" / "out"
    next_index_path = next_out_dir / "index.html"
    next_assets_dir = next_out_dir / "_next"

    if next_assets_dir.is_dir():
        app.mount(
            "/_next",
            StaticFiles(directory=str(next_assets_dir)),
            name="next-static-assets",
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def ui_home() -> HTMLResponse:
        target = next_index_path if next_index_path.is_file() else fallback_ui_path
        return HTMLResponse(target.read_text(encoding="utf-8"))

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        engine: SearchEngine = request.app.state.engine
        p_engine: ParallelSearchEngine | None = request.app.state.parallel_engine
        return {
            "status": "ok",
            "total_documents": engine.index.total_docs,
            "parallel_active": bool(p_engine and p_engine.is_running),
            "parallel_workers": p_engine.num_workers if p_engine else 0,
        }

    @app.get("/stats")
    def stats(request: Request) -> dict[str, Any]:
        engine: SearchEngine = request.app.state.engine
        p_engine: ParallelSearchEngine | None = request.app.state.parallel_engine
        data = engine.stats()
        data["parallel_active"] = bool(p_engine and p_engine.is_running)
        data["parallel_workers"] = p_engine.num_workers if p_engine else 0
        return data

    @app.post(
        "/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_or_upsert_document(
        payload: DocumentCreateRequest,
        request: Request,
    ) -> DocumentResponse:
        engine: SearchEngine = request.app.state.engine
        rec = engine.add_document(
            title=payload.title,
            content=payload.content,
            external_id=payload.external_id,
            metadata=payload.metadata,
        )
        return DocumentResponse.from_record(rec)

    @app.post(
        "/documents/batch",
        response_model=list[DocumentResponse],
        status_code=status.HTTP_201_CREATED,
    )
    def batch_create_documents(
        payload: BatchDocumentsRequest,
        request: Request,
    ) -> list[DocumentResponse]:
        engine: SearchEngine = request.app.state.engine
        records = engine.add_documents_batch([d.model_dump() for d in payload.documents])
        return [DocumentResponse.from_record(r) for r in records]

    @app.post(
        "/documents/upload",
        response_model=list[DocumentResponse],
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_documents(
        request: Request,
        files: list[UploadFile] = File(...),
    ) -> list[DocumentResponse]:
        engine: SearchEngine = request.app.state.engine
        payloads: list[tuple[str, bytes]] = []
        for upload in files:
            filename = upload.filename or "untitled.txt"
            raw = await upload.read()
            payloads.append((filename, raw))
        try:
            records = import_uploaded_files(engine=engine, files=payloads)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return [DocumentResponse.from_record(r) for r in records]

    @app.post("/documents/import-directory")
    def import_dir_endpoint(
        payload: ImportDirectoryRequest,
        request: Request,
    ) -> dict[str, Any]:
        engine: SearchEngine = request.app.state.engine
        try:
            records = import_directory(
                engine=engine,
                directory=payload.directory,
                extensions=tuple(payload.extensions),
                recursive=payload.recursive,
            )
        except NotADirectoryError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return {
            "imported_count": len(records),
            "doc_ids": [r.doc_id for r in records],
        }

    @app.get("/documents", response_model=list[DocumentResponse])
    def list_documents(
        request: Request,
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> list[DocumentResponse]:
        engine: SearchEngine = request.app.state.engine
        records = engine.list_documents(limit=limit, offset=offset)
        return [DocumentResponse.from_record(r) for r in records]

    @app.get("/documents/{doc_id}", response_model=DocumentResponse)
    def get_document(doc_id: int, request: Request) -> DocumentResponse:
        engine: SearchEngine = request.app.state.engine
        rec = engine.get_document(doc_id)
        if rec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_id} not found.",
            )
        return DocumentResponse.from_record(rec)

    @app.put("/documents/{doc_id}", response_model=DocumentResponse)
    def update_document(
        doc_id: int,
        payload: DocumentUpdateRequest,
        request: Request,
    ) -> DocumentResponse:
        engine: SearchEngine = request.app.state.engine
        rec = engine.update_document(
            doc_id=doc_id,
            title=payload.title,
            content=payload.content,
            metadata=payload.metadata,
        )
        if rec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_id} not found.",
            )
        return DocumentResponse.from_record(rec)

    @app.delete("/documents/{doc_id}")
    def delete_document(doc_id: int, request: Request) -> dict[str, Any]:
        engine: SearchEngine = request.app.state.engine
        deleted = engine.delete_document(doc_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {doc_id} not found.",
            )
        return {"deleted": True, "doc_id": doc_id}

    @app.post("/index/rebuild")
    def rebuild_index(request: Request) -> dict[str, int]:
        engine: SearchEngine = request.app.state.engine
        return engine.rebuild_index()

    @app.get("/search", response_model=SearchApiResponse)
    def search_get(
        request: Request,
        q: str = Query(..., min_length=1),
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        operator: Literal["AND", "OR"] = Query(default="AND"),
        include_content: bool = Query(default=True),
        parallel: bool = Query(default=False),
    ) -> SearchApiResponse:
        return _execute_search(
            app=request.app,
            q=q,
            limit=limit,
            offset=offset,
            operator=operator,
            include_content=include_content,
            parallel=parallel,
        )

    @app.post("/search", response_model=SearchApiResponse)
    def search_post(
        payload: SearchQueryRequest,
        request: Request,
    ) -> SearchApiResponse:
        return _execute_search(
            app=request.app,
            q=payload.q,
            limit=payload.limit,
            offset=payload.offset,
            operator=payload.operator,
            include_content=payload.include_content,
            parallel=payload.parallel,
        )

    return app


app = create_app()

