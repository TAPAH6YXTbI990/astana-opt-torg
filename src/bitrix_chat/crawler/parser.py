from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from docling.datamodel.base_models import DocumentStream
from docling.datamodel.document import DoclingDocument
from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)

_converter: Optional[DocumentConverter] = None


def _get_converter() -> DocumentConverter:
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter


def parse_html(html_bytes: bytes, name: str = "page.html") -> DoclingDocument:
    """Parse cleaned HTML bytes into a DoclingDocument using docling."""
    converter = _get_converter()
    stream = DocumentStream(name=name, stream=BytesIO(html_bytes))
    result = converter.convert(stream)
    if result is None or result.document is None:
        raise RuntimeError("docling returned an empty conversion result")
    return result.document
