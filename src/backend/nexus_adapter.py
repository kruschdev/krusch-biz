"""
src/backend/nexus_adapter.py
============================
Universal document ingestion adapter for KruschBiz.
Integrates with `krusch_nexus` when available, and provides high-fidelity
in-process fallback parsing and chunking for standalone / containerized deployments.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger("kruschbiz.nexus_adapter")

DEFAULT_PAGE_BBOX = [0.0, 0.0, 612.0, 792.0]
_nexus_lock = threading.Lock()

try:
    import pypdf  # noqa: F401
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

# Check if krusch_nexus is installed
_NEXUS_AVAILABLE = False
try:
    import krusch_nexus.chunking  # noqa: F401
    import krusch_nexus.parsers  # noqa: F401
    _NEXUS_AVAILABLE = True
    logger.info("krusch_nexus detected. Using native high-throughput document ingestion engine.")
except ImportError:
    import sys
    candidate_paths = [
        os.getenv("KRUSCH_NEXUS_PATH"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "krusch-nexus", "src"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "krusch-nexus", "src"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "krusch-nexus", "src"),
        "/nexus/src",
        os.path.expanduser("~/homelab/projects/krusch-nexus/src"),
    ]
    for p in candidate_paths:
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
            break
    try:
        import krusch_nexus.chunking  # noqa: F401
        import krusch_nexus.parsers  # noqa: F401
        _NEXUS_AVAILABLE = True
        logger.info("krusch_nexus detected via monorepo candidate path. Using native high-throughput document ingestion engine.")
    except ImportError:
        logger.info("krusch_nexus not detected in environment. Using sovereign standalone parser adapter.")


@dataclass
class ParsedPage:
    page_number: int = 1
    text: str = ""
    tables: list[list[str]] = field(default_factory=list)
    bbox: list[float] = field(default_factory=lambda: list(DEFAULT_PAGE_BBOX))


@dataclass
class ParsedDocument:
    filename: str
    extension: str
    pages: list[ParsedPage]
    total_pages: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)


@dataclass
class DocumentChunk:
    text: str
    page_number: int | None
    section_locator: str | None
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentParser(Protocol):
    """Protocol for pluggable document parsers (Nexus, Poppler, PyPDF, Standalone)."""
    def parse(self, file_path: str) -> ParsedDocument:
        ...


def is_poppler_available() -> bool:
    """Return True if poppler pdftotext binary is available on PATH."""
    return shutil.which("pdftotext") is not None


def is_pypdf_available() -> bool:
    """Return True if pypdf is installed in the current Python environment."""
    return _PYPDF_AVAILABLE


def is_nexus_available() -> bool:
    """Return True if external krusch_nexus library is present in environment."""
    with _nexus_lock:
        return _NEXUS_AVAILABLE


def parse_document(file_path: str) -> ParsedDocument:
    """Parse document via krusch_nexus or high-fidelity standalone fallback."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    if is_nexus_available():
        try:
            import krusch_nexus
            res = krusch_nexus.parse_file(file_path)
            pages = []
            for idx, p in enumerate(getattr(res, "pages", [])):
                p_num = getattr(p, "page_number", None)
                if p_num is None and ext in (".pdf", ".docx", ".doc"):
                    p_num = getattr(p, "index", None)
                if p_num is None:
                    p_num = idx + 1
                p_text = getattr(p, "text", "")
                p_tables = getattr(p, "tables", [])
                p_bbox = getattr(p, "bbox", None) or list(DEFAULT_PAGE_BBOX)
                pages.append(ParsedPage(page_number=int(p_num), text=p_text, tables=p_tables, bbox=list(p_bbox)))
            meta = dict(getattr(res, "metadata", {}) or {})
            meta["nexus_result"] = res
            meta["file_path"] = file_path
            meta["file_hash"] = getattr(res, "file_hash", None)
            return ParsedDocument(
                filename=filename,
                extension=ext,
                pages=pages if pages else [ParsedPage(page_number=1, text=getattr(res, "text", ""))],
                total_pages=len(pages) if pages else 1,
                metadata=meta
            )
        except Exception as e:
            logger.warning(f"krusch_nexus parsing encountered error ({e}); falling back to standalone parser.")

    # Standalone Fallback Implementation
    pages: list[ParsedPage] = []

    if ext in (".txt", ".md", ".json"):
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        pages.append(ParsedPage(page_number=1, text=content))

    elif ext == ".csv":
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for r in reader:
                rows.append(", ".join(r))
        pages.append(ParsedPage(page_number=1, text="\n".join(rows)))

    elif ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(file_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            pages.append(ParsedPage(page_number=1, text="\n\n".join(paras)))
        except Exception as de:
            logger.warning(f"Docx extraction error: {de}")
            pages.append(ParsedPage(page_number=1, text=f"[Docx parse error: {de}]"))

    elif ext == ".pdf":
        if not _PYPDF_AVAILABLE:
            logger.warning("pypdf is not installed; falling back to placeholder page for PDF extraction.")
            pages.append(ParsedPage(page_number=1, text="[PDF extraction notice: pypdf not installed]"))
        else:
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                for idx, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages.append(ParsedPage(page_number=idx + 1, text=text))
            except Exception as pe:
                logger.warning(f"PDF extraction error: {pe}")
                pages.append(ParsedPage(page_number=1, text=f"[PDF extraction notice: {pe}]"))

    else:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            pages.append(ParsedPage(page_number=1, text=f.read()))

    return ParsedDocument(
        filename=filename,
        extension=ext,
        pages=pages,
        total_pages=len(pages)
    )


def chunk_document(
    parsed_doc: ParsedDocument,
    max_chunk_chars: int = 1500,
    overlap_chars: int = 150
) -> list[DocumentChunk]:
    """
    Chunk document by natural legal boundaries (Sections, Articles, Paragraphs).
    Preserves hierarchical section locators, bounding boxes, character spans, and page numbers.
    Delegates to KruschNexus citation spine when available.
    """
    if _NEXUS_AVAILABLE and parsed_doc.metadata.get("nexus_result"):
        try:
            from krusch_nexus.chunking import chunk_document_pages
            nexus_res = parsed_doc.metadata["nexus_result"]
            file_hash = parsed_doc.metadata.get("file_hash") or getattr(nexus_res, "file_hash", None)
            if not file_hash:
                import hashlib
                file_hash = hashlib.sha256(parsed_doc.full_text.encode("utf-8")).hexdigest()
            nexus_chunks = chunk_document_pages(
                pages=nexus_res.pages,
                filename=parsed_doc.filename,
                file_hash=file_hash,
                max_chars=max_chunk_chars,
                overlap_chars=overlap_chars,
                base_metadata={"consumer": "krusch_biz"}
            )
            chunks: list[DocumentChunk] = []
            for ch in nexus_chunks:
                hdr = ch.header or ch.locator
                if ch.page_number is not None:
                    sec_loc = f"p. {ch.page_number} § {hdr}" if hdr else f"p. {ch.page_number}"
                else:
                    sec_loc = hdr or "General"

                ch_meta = ch.to_dict()
                if not ch_meta.get("bbox"):
                    ch_meta["bbox"] = list(DEFAULT_PAGE_BBOX)
                if ch_meta.get("char_start") is None:
                    ch_meta["char_start"] = 0
                if ch_meta.get("char_end") is None:
                    ch_meta["char_end"] = len(ch.text)

                chunks.append(DocumentChunk(
                    text=ch.text,
                    page_number=ch.page_number if ch.page_number is not None else 1,
                    section_locator=sec_loc,
                    chunk_index=ch.chunk_index,
                    metadata=ch_meta
                ))
            if chunks:
                return chunks
        except Exception as e:
            logger.warning(f"krusch_nexus chunking failed ({e}); falling back to standalone chunker.")

    chunks: list[DocumentChunk] = []
    chunk_idx = 0
    default_bbox = list(DEFAULT_PAGE_BBOX)

    section_pattern = re.compile(
        r"(?=(?:^|\n)(?:#+\s*)?(?:(?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|CLAUSE)\s+[\dA-Z\.]+|§\s*[\dA-Z\.]+))",
        re.IGNORECASE
    )
    header_prefix_re = re.compile(
        r"^(?:#+\s*)?((?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|CLAUSE)\s+[\dA-Z\.]+|§\s*[\dA-Z\.]+)",
        re.IGNORECASE
    )

    for page in parsed_doc.pages:
        text = page.text.strip()
        if not text:
            continue

        raw_sections = [b.strip() for b in section_pattern.split(text) if b and b.strip()]
        if (
            parsed_doc.extension == ".pdf"
            and len(raw_sections) >= 2
            and not header_prefix_re.match(raw_sections[0])
            and len(raw_sections[0]) < 120
        ):
            # Merge short document title preamble on PDF page into the first section block (BUG-02)
            first_hdr = header_prefix_re.match(raw_sections[1])
            raw_sections[1] = f"{raw_sections[0]}\n{raw_sections[1]}"
            raw_sections.pop(0)
            p_num = page.page_number if page.page_number is not None else 1
            printed_page = str(p_num)
            if first_hdr:
                hdr_title = first_hdr.group(1).title()
                current_section_locator = f"p. {p_num} § {hdr_title}"
            else:
                current_section_locator = f"p. {p_num}"
        else:
            p_num = page.page_number if page.page_number is not None else 1
            printed_page = str(p_num)
            current_section_locator = f"p. {p_num}"

        char_cursor = 0

        for block in raw_sections:
            block = block.strip()
            if not block:
                continue

            # Identify if block starts with a section header
            sec_header_match = header_prefix_re.match(block)
            if sec_header_match:
                hdr_title = sec_header_match.group(1).title()
                current_section_locator = (
                    f"p. {p_num} § {hdr_title}" if parsed_doc.extension == ".pdf" else hdr_title
                )

            # Split block if it exceeds max size
            if len(block) <= max_chunk_chars:
                c_start = char_cursor
                c_end = c_start + len(block)
                char_cursor = c_end + 1
                chunks.append(DocumentChunk(
                    text=block,
                    page_number=page.page_number,
                    section_locator=current_section_locator,
                    chunk_index=chunk_idx,
                    metadata={
                        "printed_page": printed_page,
                        "bbox": list(default_bbox),
                        "char_start": c_start,
                        "char_end": c_end,
                        "extra": {"parser": "standalone_fallback"},
                    },
                ))
                chunk_idx += 1
            else:
                paragraphs = block.split("\n\n")
                buffer = ""
                for p in paragraphs:
                    p = p.strip()
                    if not p:
                        continue
                    if len(buffer) + len(p) + 2 > max_chunk_chars and buffer:
                        c_start = char_cursor
                        c_end = c_start + len(buffer)
                        char_cursor = c_end + 2
                        chunks.append(DocumentChunk(
                            text=buffer,
                            page_number=page.page_number,
                            section_locator=current_section_locator,
                            chunk_index=chunk_idx,
                            metadata={
                                "printed_page": printed_page,
                                "bbox": list(default_bbox),
                                "char_start": c_start,
                                "char_end": c_end,
                                "extra": {"parser": "standalone_fallback"},
                            },
                        ))
                        chunk_idx += 1
                        buffer = p
                    else:
                        buffer = f"{buffer}\n\n{p}".strip() if buffer else p

                if buffer:
                    c_start = char_cursor
                    c_end = c_start + len(buffer)
                    char_cursor = c_end + 2
                    chunks.append(DocumentChunk(
                        text=buffer,
                        page_number=page.page_number,
                        section_locator=current_section_locator,
                        chunk_index=chunk_idx,
                        metadata={
                            "printed_page": printed_page,
                            "bbox": list(default_bbox),
                            "char_start": c_start,
                            "char_end": c_end,
                            "extra": {"parser": "standalone_fallback"},
                        },
                    ))
                    chunk_idx += 1

    return chunks
