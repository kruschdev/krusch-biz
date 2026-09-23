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
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("kruschbiz.nexus_adapter")

# Check if krusch_nexus is installed
_NEXUS_AVAILABLE = False
try:
    import krusch_nexus.chunking  # noqa: F401
    import krusch_nexus.parsers  # noqa: F401
    _NEXUS_AVAILABLE = True
    logger.info("krusch_nexus detected. Using native high-throughput document ingestion engine.")
except ImportError:
    logger.info("krusch_nexus not detected in environment. Using sovereign standalone parser adapter.")


@dataclass
class ParsedPage:
    page_number: int
    text: str
    tables: list[list[str]] = field(default_factory=list)


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


def is_nexus_available() -> bool:
    """Return True if external krusch_nexus library is present in environment."""
    return _NEXUS_AVAILABLE


def parse_document(file_path: str) -> ParsedDocument:
    """Parse document via krusch_nexus or high-fidelity standalone fallback."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    if _NEXUS_AVAILABLE:
        try:
            import krusch_nexus.parsers as kn_parsers
            res = kn_parsers.parse_document(file_path, filename)
            pages = []
            for p in getattr(res, "pages", []):
                p_num = getattr(p, "page_number", 1)
                p_text = getattr(p, "text", "")
                p_tables = getattr(p, "tables", [])
                pages.append(ParsedPage(page_number=p_num, text=p_text, tables=p_tables))
            return ParsedDocument(
                filename=filename,
                extension=ext,
                pages=pages if pages else [ParsedPage(page_number=1, text=getattr(res, "text", ""))],
                total_pages=len(pages) if pages else 1,
                metadata=getattr(res, "metadata", {})
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
    Preserves hierarchical section locators and page numbers.
    """
    chunks: list[DocumentChunk] = []
    chunk_idx = 0

    section_pattern = re.compile(
        r"(?=(?:^|\n)(?:#+\s*)?(?:(?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|CLAUSE)\s+[\dA-Z\.]+|§\s*[\dA-Z\.]+))",
        re.IGNORECASE
    )

    for page in parsed_doc.pages:
        text = page.text.strip()
        if not text:
            continue

        raw_sections = section_pattern.split(text)
        p_num = page.page_number if page.page_number is not None else 1
        current_section_locator = f"p. {p_num}"

        for block in raw_sections:
            block = block.strip()
            if not block:
                continue

            # Identify if block starts with a section header
            sec_header_match = re.match(
                r"^(?:#+\s*)?((?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|CLAUSE)\s+[\dA-Z\.]+|§\s*[\dA-Z\.]+)",
                block,
                re.IGNORECASE
            )
            if sec_header_match:
                current_section_locator = sec_header_match.group(1).title()

            # Split block if it exceeds max size
            if len(block) <= max_chunk_chars:
                chunks.append(DocumentChunk(
                    text=block,
                    page_number=page.page_number,
                    section_locator=current_section_locator,
                    chunk_index=chunk_idx,
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
                        chunks.append(DocumentChunk(
                            text=buffer,
                            page_number=page.page_number,
                            section_locator=current_section_locator,
                            chunk_index=chunk_idx,
                        ))
                        chunk_idx += 1
                        buffer = p
                    else:
                        buffer = f"{buffer}\n\n{p}".strip() if buffer else p

                if buffer:
                    chunks.append(DocumentChunk(
                        text=buffer,
                        page_number=page.page_number,
                        section_locator=current_section_locator,
                        chunk_index=chunk_idx,
                    ))
                    chunk_idx += 1

    return chunks
