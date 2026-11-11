"""Document import and text extraction utilities (TXT, MD, PDF, DOCX) for SearchCore."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from searchcore.index import SearchEngine
from searchcore.storage import DocumentRecord

SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".csv",
    ".json",
    ".log",
)

_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _extract_title(path: Path, content: str) -> str:
    """Derive a document title from the first markdown heading or filename stem."""
    if path.suffix.lower() in (".md", ".txt"):
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                if heading:
                    return heading
            elif stripped:
                break
    return path.stem


def extract_text_from_bytes(
    filename: str,
    raw_bytes: bytes,
    encoding: str = "utf-8",
) -> str:
    """Extract searchable plain text from TXT, MD, PDF, DOCX, and text-based files."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p and p.strip())
        if not text:
            raise ValueError(f"No extractable text found in PDF '{filename}' (it may be scanned/image-only).")
        return text

    if ext == ".docx":
        from docx import Document

        doc = Document(io.BytesIO(raw_bytes))
        parts: list[str] = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                if row_cells:
                    parts.append(" | ".join(row_cells))
        text = "\n".join(parts)
        if not text:
            raise ValueError(f"No extractable text found in DOCX '{filename}'.")
        return text

    if ext == ".doc" and raw_bytes.startswith(_OLE2_MAGIC):
        raise ValueError(
            f"Legacy binary .doc file '{filename}' is not supported; convert it to .docx or .pdf."
        )

    return raw_bytes.decode(encoding, errors="replace")


def import_text_file(
    engine: SearchEngine,
    file_path: str | Path,
    external_id: str | None = None,
    title: str | None = None,
    metadata: dict[str, Any] | None = None,
    encoding: str = "utf-8",
) -> DocumentRecord:
    """Read a supported document file (TXT, MD, PDF, DOCX) and upsert it into SearchEngine."""
    path = Path(file_path)
    raw_bytes = path.read_bytes()
    content = extract_text_from_bytes(path.name, raw_bytes, encoding=encoding)
    doc_title = title if title is not None else _extract_title(path, content)
    doc_external_id = external_id if external_id is not None else str(path.resolve())
    doc_metadata = {
        "source_path": str(path),
        "extension": path.suffix.lower(),
        **(metadata or {}),
    }
    return engine.add_document(
        title=doc_title,
        content=content,
        external_id=doc_external_id,
        metadata=doc_metadata,
    )


def import_uploaded_files(
    engine: SearchEngine,
    files: list[tuple[str, bytes]],
    encoding: str = "utf-8",
) -> list[DocumentRecord]:
    """Extract text and batch-upsert uploaded (filename, bytes) pairs into SearchEngine."""
    batch: list[dict[str, Any]] = []
    for filename, raw_bytes in files:
        path = Path(filename)
        content = extract_text_from_bytes(path.name, raw_bytes, encoding=encoding)
        batch.append(
            {
                "external_id": path.name,
                "title": _extract_title(path, content),
                "content": content,
                "metadata": {
                    "filename": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": len(raw_bytes),
                },
            }
        )
    if not batch:
        return []
    return engine.add_documents_batch(batch)


def import_directory(
    engine: SearchEngine,
    directory: str | Path,
    extensions: tuple[str, ...] = (".txt", ".md", ".pdf", ".docx"),
    recursive: bool = True,
    encoding: str = "utf-8",
) -> list[DocumentRecord]:
    """Import all matching document files from a directory in a single batch transaction."""
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"Directory does not exist: {root}")

    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    iterator = root.rglob("*") if recursive else root.glob("*")
    files = sorted(p for p in iterator if p.is_file() and p.suffix.lower() in ext_set)

    batch: list[dict[str, Any]] = []
    for path in files:
        raw_bytes = path.read_bytes()
        content = extract_text_from_bytes(path.name, raw_bytes, encoding=encoding)
        rel_id = path.relative_to(root).as_posix()
        batch.append(
            {
                "external_id": rel_id,
                "title": _extract_title(path, content),
                "content": content,
                "metadata": {
                    "source_path": str(path),
                    "relative_path": rel_id,
                    "extension": path.suffix.lower(),
                },
            }
        )

    if not batch:
        return []
    return engine.add_documents_batch(batch)
