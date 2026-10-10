"""Shared pytest fixtures: sample PDFs and images built on the fly."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter


def write_blank_pdf(path: Path, pages: int) -> Path:
    """Write a PDF with *pages* blank A4 pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595.28, height=841.89)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def write_noise_png(path: Path, size: tuple[int, int] = (1200, 1200)) -> Path:
    """Write a noisy PNG (incompressible, so downscaling shows real savings)."""
    rng = random.Random(42)
    image = Image.new("RGB", size)
    image.putdata(
        [(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])]
    )
    image.save(path, "PNG")
    return path


def write_image_pdf(path: Path, png: Path) -> Path:
    """Write a one-page PDF embedding *png* at full page size."""
    with Image.open(png) as image:
        image.convert("RGB").save(path, "PDF")
    return path


@pytest.fixture()
def tmp_pdf(tmp_path: Path):
    def _make(name: str, pages: int) -> Path:
        return write_blank_pdf(tmp_path / name, pages)

    return _make
