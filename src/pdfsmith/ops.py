"""Core PDF operations.

Thin, testable functions with no argparse and no printing. Every function
returns a small report dataclass; errors surface as ``PdfInputError`` /
``PdfOutputError`` for the CLI to translate into exit codes.
"""

from __future__ import annotations

import io as stdlib_io
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image
from pypdf import PdfWriter

from .errors import PdfInputError, PdfOutputError
from .io import PathLike, atomic_write_pdf, plan_output, read_pdf, staged_output
from .ranges import parse_page_ranges

POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4
A4_WIDTH_PT = 595.28  # 210 mm
A4_HEIGHT_PT = 841.89  # 297 mm
DEFAULT_COMPRESS_DPI = 150
A4_RASTER_DPI = 150
IMAGE_PAGE_SIZES = ("fit", "a4")


@dataclass(frozen=True)
class MergeReport:
    """Outcome of :func:`merge_pdfs`."""

    inputs: tuple[str, ...]
    total_pages: int
    output: str


@dataclass(frozen=True)
class SplitReport:
    """Outcome of :func:`split_pdf`."""

    input: str
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class CompressReport:
    """Outcome of :func:`compress_pdf`."""

    input: str
    output: str
    level: int
    size_before: int
    size_after: int
    images_downscaled: int

    @property
    def saved_bytes(self) -> int:
        """Bytes saved by the compression (may be 0 or negative)."""
        return self.size_before - self.size_after


@dataclass(frozen=True)
class ImagesReport:
    """Outcome of :func:`images_to_pdf`."""

    inputs: tuple[str, ...]
    output: str
    page_size: str


@dataclass(frozen=True)
class PdfInfo:
    """Read-only summary of a PDF, from :func:`pdf_info`."""

    path: str
    pages: int
    width_mm: float
    height_mm: float
    title: str | None
    author: str | None
    images: int


def merge_pdfs(
    inputs: Sequence[PathLike],
    output: PathLike,
    *,
    title: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> MergeReport:
    """Concatenate *inputs* in order into a single PDF at *output*."""
    sources = [Path(item) for item in inputs]
    if len(sources) < 2:
        raise PdfInputError(
            f"merge needs at least two input PDFs (got {len(sources)})"
        )
    readers = [read_pdf(source) for source in sources]
    total_pages = sum(len(reader.pages) for reader in readers)
    if total_pages == 0:
        raise PdfInputError("nothing to merge: all inputs are empty")
    destination = plan_output(output, force=force)
    report = MergeReport(
        inputs=tuple(str(source) for source in sources),
        total_pages=total_pages,
        output=str(destination),
    )
    if dry_run:
        return report
    writer = PdfWriter()
    for reader in readers:
        for page in reader.pages:
            writer.add_page(page)
    if title:
        writer.add_metadata({"/Title": title})
    atomic_write_pdf(writer, destination)
    return report


def split_pdf(
    input: PathLike,
    out_dir: PathLike,
    *,
    ranges: str | None = None,
    prefix: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> SplitReport:
    """Split *input* into several PDFs inside *out_dir*.

    Without *ranges*, one file per page is produced. With a spec like
    ``"1-3,5"``, each chunk becomes one file named ``<prefix>-<n>.pdf``.
    """
    reader = read_pdf(input)
    page_count = len(reader.pages)
    if page_count == 0:
        raise PdfInputError(f"'{input}' has no pages to split")
    parsed = (
        parse_page_ranges(ranges, page_count)
        if ranges is not None
        else [(index, index) for index in range(page_count)]
    )
    directory = Path(out_dir)
    stem = prefix or Path(input).stem
    destinations = [
        plan_output(directory / f"{stem}-{number}.pdf", force=force)
        for number, _ in enumerate(parsed, start=1)
    ]
    report = SplitReport(
        input=str(input), outputs=tuple(str(path) for path in destinations)
    )
    if dry_run:
        return report
    for destination, (first, last) in zip(destinations, parsed):
        writer = PdfWriter()
        for index in range(first, last + 1):
            writer.add_page(reader.pages[index])
        atomic_write_pdf(writer, destination)
    return report


def compress_pdf(
    input: PathLike,
    output: PathLike,
    *,
    level: int = 1,
    dpi: int = DEFAULT_COMPRESS_DPI,
    force: bool = False,
    dry_run: bool = False,
) -> CompressReport:
    """Shrink *input* and write the result to *output*.

    Level 1 is lossless: content streams are recompressed and duplicate
    objects are merged. Level 2 additionally downscales raster images that
    render above *dpi*, which is where the big savings come from.
    """
    if level not in (1, 2):
        raise PdfInputError(f"unknown compress level {level} (choose 1 or 2)")
    if dpi <= 0:
        raise PdfInputError(f"bad dpi {dpi} (must be a positive integer)")
    reader = read_pdf(input)
    if len(reader.pages) == 0:
        raise PdfInputError(f"'{input}' has no pages to compress")
    size_before = Path(input).stat().st_size
    destination = plan_output(output, force=force)
    if dry_run:
        return CompressReport(
            input=str(input),
            output=str(destination),
            level=level,
            size_before=size_before,
            size_after=0,
            images_downscaled=0,
        )
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    for page in writer.pages:
        page.compress_content_streams()
    downscaled = 0
    if level >= 2:
        for page in writer.pages:
            downscaled += _downscale_page_images(page, dpi)
    writer.compress_identical_objects()
    atomic_write_pdf(writer, destination)
    size_after = destination.stat().st_size
    return CompressReport(
        input=str(input),
        output=str(destination),
        level=level,
        size_before=size_before,
        size_after=size_after,
        images_downscaled=downscaled,
    )


def _page_dpi(page: object, image_width_px: int) -> float | None:
    """Estimate the rendered DPI of an image spanning the page width."""
    try:
        width_pt = float(page.mediabox.width)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return None
    if width_pt <= 0:
        return None
    return image_width_px / (width_pt / POINTS_PER_INCH)


def _downscale_page_images(page: object, target_dpi: int) -> int:
    """Downscale raster images above *target_dpi* in place.

    Returns the number of images actually downscaled. Inline images and any
    image pypdf cannot replace are skipped rather than failing the run.
    """
    downscaled = 0
    for image in page.images:  # type: ignore[attr-defined]
        try:
            pil_image = Image.open(stdlib_io.BytesIO(image.data))
            pil_image.load()
        except Exception:  # noqa: BLE001 - corrupt/odd images are skipped
            continue
        rendered_dpi = _page_dpi(page, pil_image.width)
        if rendered_dpi is None or rendered_dpi <= target_dpi:
            continue
        scale = target_dpi / rendered_dpi
        new_size = (
            max(1, int(pil_image.width * scale)),
            max(1, int(pil_image.height * scale)),
        )
        resized = pil_image.resize(new_size, Image.LANCZOS)
        try:
            image.replace(resized)
        except TypeError:
            continue  # inline or otherwise non-replaceable image
        downscaled += 1
    return downscaled


def images_to_pdf(
    images: Sequence[PathLike],
    output: PathLike,
    *,
    page_size: str = "fit",
    force: bool = False,
    dry_run: bool = False,
) -> ImagesReport:
    """Convert *images* into a multi-page PDF, one image per page.

    ``page_size="fit"`` sizes each page to its image; ``"a4"`` fits every
    image onto an A4 page, preserving aspect ratio.
    """
    if page_size not in IMAGE_PAGE_SIZES:
        raise PdfInputError(
            f"unknown page size '{page_size}' (choose from: {', '.join(IMAGE_PAGE_SIZES)})"
        )
    sources = [Path(item) for item in images]
    if not sources:
        raise PdfInputError("images needs at least one image file")
    pages: list[Image.Image] = [_load_image(source) for source in sources]
    destination = plan_output(output, force=force)
    report = ImagesReport(
        inputs=tuple(str(source) for source in sources),
        output=str(destination),
        page_size=page_size,
    )
    if dry_run:
        return report
    prepared = [_fit_to_page(image, page_size) for image in pages]
    try:
        with staged_output(destination) as tmp:
            first, resolution = prepared[0]
            first.save(
                tmp,
                "PDF",
                resolution=resolution,
                title=destination.stem,  # Pillow titles the PDF from the filename
                save_all=True,
                append_images=[image for image, _ in prepared[1:]],
            )
    except OSError as exc:
        raise PdfOutputError(f"cannot write '{destination}': {exc}") from exc
    return report


def _load_image(source: Path) -> Image.Image:
    if not source.exists():
        raise PdfInputError(f"image not found: {source}")
    if not source.is_file():
        raise PdfInputError(f"not a file: {source}")
    try:
        with Image.open(source) as handle:
            handle.load()
            return handle.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - Pillow raises many error types
        raise PdfInputError(f"cannot read image '{source}': {exc}") from exc


def _fit_to_page(image: Image.Image, page_size: str) -> tuple[Image.Image, float]:
    """Fit *image* to a page; returns the raster plus its save resolution (dpi).

    ``"fit"`` keeps the image untouched at 72 dpi (page size == image size).
    ``"a4"`` rasterizes at A4_RASTER_DPI onto an A4 canvas so the page is a
    true A4 (210 x 297 mm) however it is viewed.
    """
    if page_size == "fit":
        return image, 72.0
    canvas_width = int(A4_WIDTH_PT / POINTS_PER_INCH * A4_RASTER_DPI)
    canvas_height = int(A4_HEIGHT_PT / POINTS_PER_INCH * A4_RASTER_DPI)
    scale = min(canvas_width / image.width, canvas_height / image.height)
    fitted = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
    canvas.paste(fitted, ((canvas_width - fitted.width) // 2, (canvas_height - fitted.height) // 2))
    return canvas, float(A4_RASTER_DPI)


def pdf_info(input: PathLike) -> PdfInfo:
    """Return a read-only summary of *input*."""
    reader = read_pdf(input)
    pages = len(reader.pages)
    width_mm = height_mm = 0.0
    if pages:
        box = reader.pages[0].mediabox
        width_mm = float(box.width) / POINTS_PER_INCH * MM_PER_INCH
        height_mm = float(box.height) / POINTS_PER_INCH * MM_PER_INCH
    metadata = reader.metadata
    return PdfInfo(
        path=str(input),
        pages=pages,
        width_mm=width_mm,
        height_mm=height_mm,
        title=getattr(metadata, "title", None),
        author=getattr(metadata, "author", None),
        images=sum(len(page.images) for page in reader.pages),
    )
