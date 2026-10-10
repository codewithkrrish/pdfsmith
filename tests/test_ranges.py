"""Tests for page-range parsing."""

from __future__ import annotations

import pytest

from pdfsmith.errors import PdfInputError
from pdfsmith.ranges import parse_page_ranges


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("1", [(0, 0)]),
        ("1-3", [(0, 2)]),
        ("1-3,5", [(0, 2), (4, 4)]),
        ("8-", [(7, 9)]),  # open end resolves against the page count
        ("1-2, 4 - 5", [(0, 1), (3, 4)]),  # whitespace is tolerated
        ("3-3", [(2, 2)]),
    ],
)
def test_valid_specs(spec: str, expected: list[tuple[int, int]]) -> None:
    assert parse_page_ranges(spec, page_count=10) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "   ",
        "abc",
        "0",  # pages start at 1
        "0-2",
        "3-1",  # reversed
        "11-",  # start beyond the document
        "1-11",  # end beyond the document
        "11",
        "1,,3",  # empty chunk
        "1.5",
    ],
)
def test_invalid_specs(spec: str) -> None:
    with pytest.raises(PdfInputError):
        parse_page_ranges(spec, page_count=10)
