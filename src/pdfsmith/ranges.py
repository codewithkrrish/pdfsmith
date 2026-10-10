"""Parse human page-range specs like ``"1-3,5,8-"``.

Pages are 1-based in the spec (as users expect) and converted to zero-based
inclusive ``(start, end)`` tuples for internal use.
"""

from __future__ import annotations

from .errors import PdfInputError


def parse_page_ranges(spec: str, page_count: int) -> list[tuple[int, int]]:
    """Parse *spec* into zero-based inclusive ``(start, end)`` page ranges.

    Args:
        spec: Comma-separated ranges, e.g. ``"1-3,5,8-"``. A trailing dash
            (``"8-"``) means "up to the last page".
        page_count: Number of pages in the document, for validation.

    Raises:
        PdfInputError: On empty specs, non-numeric pages, reversed ranges
            (``"3-1"``), or pages outside ``1..page_count``.
    """
    if not spec or not spec.strip():
        raise PdfInputError("empty page range (expected something like '1-3,5')")

    ranges: list[tuple[int, int]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            start_text, _, end_text = chunk.partition("-")
            start = _parse_page_number(start_text.strip(), chunk)
            end = page_count if not end_text.strip() else _parse_page_number(end_text.strip(), chunk)
            if start > end:
                raise PdfInputError(
                    f"reversed range '{chunk}' (start page must be <= end page)"
                )
        else:
            start = end = _parse_page_number(chunk, chunk)
        for page in (start, end):
            if page > page_count:
                raise PdfInputError(
                    f"page {page} out of range (the PDF has {page_count} pages)"
                )
        ranges.append((start - 1, end - 1))
    if not ranges:
        raise PdfInputError("empty page range (expected something like '1-3,5')")
    return ranges


def _parse_page_number(text: str, chunk: str) -> int:
    if not text.isdigit():
        raise PdfInputError(f"bad page number in '{chunk}' (expected a positive integer)")
    page = int(text)
    if page < 1:
        raise PdfInputError(f"bad page number in '{chunk}' (pages start at 1)")
    return page
