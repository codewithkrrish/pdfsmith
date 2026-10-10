"""Thin CLI for pdfsmith: argparse wiring only.

All real work lives in :mod:`pdfsmith.ops`. Errors from the core are printed
to stderr as one human-readable line and mapped to exit codes.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, ops
from .errors import EXIT_OK, PdfsmithError

_KB = 1024


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing outputs instead of auto-renaming them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without writing anything",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the pdfsmith argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdfsmith",
        description=(
            "Swiss-army CLI for PDFs: merge, split, compress, images-to-PDF. "
            "Everything runs locally — no uploads, no watermarks, no limits."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    merge = sub.add_parser("merge", help="concatenate PDFs in order")
    merge.add_argument("inputs", nargs="+", metavar="PDF", help="input PDFs in merge order")
    merge.add_argument("-o", "--output", required=True, metavar="OUT", help="output PDF path")
    merge.add_argument("--title", default=None, help="set the document title metadata")
    _add_common(merge)

    split = sub.add_parser("split", help="split a PDF into several files")
    split.add_argument("input", metavar="PDF", help="input PDF")
    split.add_argument(
        "-o", "--out-dir", default=".", metavar="DIR", help="directory for output files (default: .)"
    )
    split.add_argument(
        "--ranges",
        default=None,
        metavar="RANGES",
        help="page ranges like '1-3,5,8-' (default: one file per page)",
    )
    split.add_argument(
        "--prefix", default=None, help="output filename stem (default: input filename)"
    )
    _add_common(split)

    compress = sub.add_parser("compress", help="shrink a PDF's file size")
    compress.add_argument("input", metavar="PDF", help="input PDF")
    compress.add_argument("-o", "--output", required=True, metavar="OUT", help="output PDF path")
    compress.add_argument(
        "--level",
        type=int,
        default=1,
        choices=(1, 2),
        help="1 = lossless stream recompression, 2 = also downscale images (default: 1)",
    )
    compress.add_argument(
        "--dpi",
        type=int,
        default=ops.DEFAULT_COMPRESS_DPI,
        help=f"target DPI for level 2 image downscaling (default: {ops.DEFAULT_COMPRESS_DPI})",
    )
    _add_common(compress)

    images = sub.add_parser("images", help="convert images into a multi-page PDF")
    images.add_argument("inputs", nargs="+", metavar="IMAGE", help="input image files in page order")
    images.add_argument("-o", "--output", required=True, metavar="OUT", help="output PDF path")
    images.add_argument(
        "--page-size",
        default="fit",
        choices=ops.IMAGE_PAGE_SIZES,
        help="fit = page per image size, a4 = fit each image onto A4 (default: fit)",
    )
    _add_common(images)

    info = sub.add_parser("info", help="show a PDF's page count, size and metadata")
    info.add_argument("input", metavar="PDF", help="input PDF")

    return parser


def _format_size(num_bytes: int) -> str:
    if num_bytes < _KB:
        return f"{num_bytes} B"
    if num_bytes < _KB * _KB:
        return f"{num_bytes / _KB:.1f} KB"
    return f"{num_bytes / (_KB * _KB):.1f} MB"


def _run_merge(args: argparse.Namespace) -> None:
    report = ops.merge_pdfs(
        args.inputs, args.output, title=args.title, force=args.force, dry_run=args.dry_run
    )
    if args.dry_run:
        print(
            f"would merge {len(report.inputs)} files "
            f"({report.total_pages} pages) -> {report.output}"
        )
        return
    print(
        f"merged {len(report.inputs)} files ({report.total_pages} pages) -> {report.output}"
    )


def _run_split(args: argparse.Namespace) -> None:
    report = ops.split_pdf(
        args.input,
        args.out_dir,
        ranges=args.ranges,
        prefix=args.prefix,
        force=args.force,
        dry_run=args.dry_run,
    )
    verb = "would split" if args.dry_run else "split"
    print(f"{verb} {report.input} into {len(report.outputs)} files:")
    for path in report.outputs:
        print(f"  {path}")


def _run_compress(args: argparse.Namespace) -> None:
    report = ops.compress_pdf(
        args.input,
        args.output,
        level=args.level,
        dpi=args.dpi,
        force=args.force,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(
            f"would compress {_format_size(report.size_before)} "
            f"-> {report.output} (level {report.level})"
        )
        return
    saved = report.saved_bytes
    percent = saved / report.size_before * 100 if report.size_before else 0.0
    line = (
        f"compressed {_format_size(report.size_before)} -> {_format_size(report.size_after)} "
        f"(saved {percent:.0f}%) -> {report.output}"
    )
    if report.level >= 2:
        line += f" [{report.images_downscaled} images downscaled]"
    print(line)


def _run_images(args: argparse.Namespace) -> None:
    report = ops.images_to_pdf(
        args.inputs,
        args.output,
        page_size=args.page_size,
        force=args.force,
        dry_run=args.dry_run,
    )
    verb = "would write" if args.dry_run else "wrote"
    print(
        f"{verb} {len(report.inputs)} images ({report.page_size} pages) -> {report.output}"
    )


def _run_info(args: argparse.Namespace) -> None:
    info = ops.pdf_info(args.input)
    print(f"path:      {info.path}")
    print(f"pages:     {info.pages}")
    print(f"page size: {info.width_mm:.1f} x {info.height_mm:.1f} mm")
    print(f"title:     {info.title or '-'}")
    print(f"author:    {info.author or '-'}")
    print(f"images:    {info.images}")


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, run the command, return the exit code."""
    args = build_parser().parse_args(argv)
    handlers = {
        "merge": _run_merge,
        "split": _run_split,
        "compress": _run_compress,
        "images": _run_images,
        "info": _run_info,
    }
    try:
        handlers[args.command](args)
    except PdfsmithError as exc:
        print(f"pdfsmith: error: {exc}", file=sys.stderr)
        return exc.exit_code
    return EXIT_OK
