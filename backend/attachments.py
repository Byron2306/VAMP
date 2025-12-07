"""Attachment download + text extraction helpers.

The extractor is defensive: unsupported formats or missing optional
dependencies result in a clear warning message instead of an exception. The
functions return both the extracted text (if any) and a metadata dict that can
be attached to evidence items.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger("vamp.attachments")


# Optional dependencies -----------------------------------------------------
try:  # PDF
    import PyPDF2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PyPDF2 = None  # type: ignore

try:  # DOCX
    import docx2txt  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    docx2txt = None  # type: ignore

try:  # PPTX
    from pptx import Presentation  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Presentation = None  # type: ignore


class AttachmentReader:
    """Lightweight attachment reader with graceful degradation."""

    def read(self, path: Path) -> Tuple[str, Dict[str, str]]:
        """Return ``(text, meta)`` for the provided attachment path."""

        if not path or not Path(path).exists():
            return "", {"read_error": "Attachment file not found"}

        path = Path(path)
        suffix = path.suffix.lower().strip()

        if suffix == ".pdf":
            return self._read_pdf(path)
        if suffix in {".doc", ".docx"}:
            return self._read_docx(path)
        if suffix in {".ppt", ".pptx"}:
            return self._read_pptx(path)

        return "", {"read_error": f"Attachment type {suffix or 'unknown'} is not supported"}

    def _read_pdf(self, path: Path) -> Tuple[str, Dict[str, str]]:
        if PyPDF2 is None:
            return "", {"read_error": "PDF extraction not supported (install PyPDF2)"}

        try:
            reader = PyPDF2.PdfReader(str(path))  # type: ignore[attr-defined]
            text_parts = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(tp.strip() for tp in text_parts if tp)
            return text, {}
        except Exception as exc:  # pragma: no cover - depends on PDF payload
            logger.warning("Failed to read PDF %s: %s", path.name, exc)
            return "", {"read_error": "Attachment could not be read"}

    def _read_docx(self, path: Path) -> Tuple[str, Dict[str, str]]:
        if docx2txt is None:
            return "", {"read_error": "DOCX extraction not supported (install docx2txt)"}
        try:
            text = docx2txt.process(str(path))  # type: ignore[operator]
            return (text or "").strip(), {}
        except Exception as exc:  # pragma: no cover - depends on document payload
            logger.warning("Failed to read DOCX %s: %s", path.name, exc)
            return "", {"read_error": "Attachment could not be read"}

    def _read_pptx(self, path: Path) -> Tuple[str, Dict[str, str]]:
        if Presentation is None:
            return "", {"read_error": "PPTX extraction not supported (install python-pptx)"}
        try:
            prs = Presentation(str(path))  # type: ignore[call-arg]
            parts = []
            for slide in prs.slides:
                for shape in getattr(slide, "shapes", []):  # type: ignore[attr-defined]
                    text = getattr(shape, "text", "")
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip(), {}
        except Exception as exc:  # pragma: no cover - depends on presentation payload
            logger.warning("Failed to read PPTX %s: %s", path.name, exc)
            return "", {"read_error": "Attachment could not be read"}


__all__ = ["AttachmentReader"]
