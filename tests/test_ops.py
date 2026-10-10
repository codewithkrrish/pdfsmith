"""Tests for the core operations: merge, split, compress, images, info."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from pdfsmith.errors import PdfInputError, PdfOutputError
from pdfsmith.io import read_pdf
from pdfsmith.ops import (
    compress_pdf,
    images_to_pdf,
    merge_pdfs,
    pdf_info,
    split_pdf,
)

from conftest import write_blank_pdf, write_image_pdf, write_noise_png


class TestMerge:
    def test_merges_pages_in_order(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 2)
        second = write_blank_pdf(tmp_path / "b.pdf", 3)
        out = tmp_path / "merged.pdf"

        report = merge_pdfs([first, second], out, title="Combined")

        assert report.total_pages == 5
        assert report.output == str(out)
        reader = PdfReader(str(out))
        assert len(reader.pages) == 5
        assert reader.metadata.title == "Combined"

    def test_needs_two_inputs(self, tmp_path: Path) -> None:
        only = write_blank_pdf(tmp_path / "a.pdf", 1)
        with pytest.raises(PdfInputError, match="at least two"):
            merge_pdfs([only], tmp_path / "out.pdf")

    def test_missing_input(self, tmp_path: Path) -> None:
        real = write_blank_pdf(tmp_path / "a.pdf", 1)
        with pytest.raises(PdfInputError, match="not found"):
            merge_pdfs([real, tmp_path / "ghost.pdf"], tmp_path / "out.pdf")

    def test_corrupt_input(self, tmp_path: Path) -> None:
        real = write_blank_pdf(tmp_path / "a.pdf", 1)
        corrupt = tmp_path / "bad.pdf"
        corrupt.write_text("this is not a pdf")
        with pytest.raises(PdfInputError, match="not a valid PDF"):
            merge_pdfs([real, corrupt], tmp_path / "out.pdf")

    def test_existing_output_is_renamed_not_overwritten(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 1)
        out = tmp_path / "merged.pdf"
        out.write_bytes(b"precious")
        report = merge_pdfs([first, second], out)
        assert report.output == str(tmp_path / "merged-2.pdf")
        assert out.read_bytes() == b"precious"

    def test_force_overwrites(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 1)
        out = tmp_path / "merged.pdf"
        out.write_bytes(b"old")
        report = merge_pdfs([first, second], out, force=True)
        assert report.output == str(out)
        assert out.read_bytes() != b"old"

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 1)
        out = tmp_path / "merged.pdf"
        report = merge_pdfs([first, second], out, dry_run=True)
        assert report.total_pages == 2
        assert not out.exists()


class TestSplit:
    def test_split_by_ranges(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 6)
        out_dir = tmp_path / "parts"

        report = split_pdf(source, out_dir, ranges="1-2,4,6")

        assert len(report.outputs) == 3
        counts = [len(PdfReader(path).pages) for path in report.outputs]
        assert counts == [2, 1, 1]

    def test_default_is_one_file_per_page(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 3)
        report = split_pdf(source, tmp_path / "parts")
        assert len(report.outputs) == 3
        assert all(len(PdfReader(path).pages) == 1 for path in report.outputs)

    def test_prefix_names_files(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 2)
        report = split_pdf(source, tmp_path / "parts", ranges="1,2", prefix="chapter")
        assert [Path(path).name for path in report.outputs] == ["chapter-1.pdf", "chapter-2.pdf"]

    def test_bad_range(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 2)
        with pytest.raises(PdfInputError, match="out of range"):
            split_pdf(source, tmp_path / "parts", ranges="1-5")

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 2)
        report = split_pdf(source, tmp_path / "parts", dry_run=True)
        assert len(report.outputs) == 2
        assert not (tmp_path / "parts").exists()


class TestCompress:
    def test_level1_is_lossless_size(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 4)
        out = tmp_path / "small.pdf"
        report = compress_pdf(source, out, level=1)
        assert len(PdfReader(str(out)).pages) == 4
        # lossless: never bigger than the input
        assert report.size_after <= report.size_before

    def test_level2_downscales_images(self, tmp_path: Path) -> None:
        # Pillow writes PDFs with the image at exactly 72 rendered dpi,
        # so the target must be below 72 to trigger a downscale here.
        png = write_noise_png(tmp_path / "big.png", size=(1200, 1200))
        source = write_image_pdf(tmp_path / "doc.pdf", png)
        out = tmp_path / "small.pdf"
        report = compress_pdf(source, out, level=2, dpi=50)
        assert report.images_downscaled == 1
        assert report.size_after < report.size_before
        assert len(PdfReader(str(out)).pages) == 1

    def test_level2_skips_small_images(self, tmp_path: Path) -> None:
        png = write_noise_png(tmp_path / "tiny.png", size=(100, 100))
        source = write_image_pdf(tmp_path / "doc.pdf", png)
        out = tmp_path / "small.pdf"
        report = compress_pdf(source, out, level=2, dpi=72)
        assert report.images_downscaled == 0

    def test_bad_level_and_dpi(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 1)
        with pytest.raises(PdfInputError, match="unknown compress level"):
            compress_pdf(source, tmp_path / "o.pdf", level=3)
        with pytest.raises(PdfInputError, match="bad dpi"):
            compress_pdf(source, tmp_path / "o.pdf", level=2, dpi=0)

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 1)
        out = tmp_path / "small.pdf"
        report = compress_pdf(source, out, dry_run=True)
        assert report.size_before > 0
        assert not out.exists()


class TestImages:
    def test_fit_pages_match_image_size(self, tmp_path: Path) -> None:
        first = write_noise_png(tmp_path / "a.png", size=(400, 300))
        second = write_noise_png(tmp_path / "b.png", size=(200, 500))
        out = tmp_path / "album.pdf"
        report = images_to_pdf([first, second], out, page_size="fit")
        reader = PdfReader(str(out))
        assert len(reader.pages) == 2
        box = reader.pages[0].mediabox
        # fit mode: page is the image at 72 dpi, so points == pixels
        assert float(box.width) == pytest.approx(400, abs=1)
        assert float(box.height) == pytest.approx(300, abs=1)
        assert report.page_size == "fit"

    def test_a4_pages(self, tmp_path: Path) -> None:
        image = write_noise_png(tmp_path / "a.png", size=(400, 300))
        out = tmp_path / "album.pdf"
        images_to_pdf([image], out, page_size="a4")
        box = PdfReader(str(out)).pages[0].mediabox
        assert float(box.width) == pytest.approx(595.28, abs=2)
        assert float(box.height) == pytest.approx(841.89, abs=2)

    def test_bad_page_size(self, tmp_path: Path) -> None:
        image = write_noise_png(tmp_path / "a.png")
        with pytest.raises(PdfInputError, match="unknown page size"):
            images_to_pdf([image], tmp_path / "o.pdf", page_size="letter")

    def test_corrupt_image(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.png"
        bad.write_text("not an image")
        with pytest.raises(PdfInputError, match="cannot read image"):
            images_to_pdf([bad], tmp_path / "o.pdf")

    def test_missing_image(self, tmp_path: Path) -> None:
        with pytest.raises(PdfInputError, match="not found"):
            images_to_pdf([tmp_path / "ghost.png"], tmp_path / "o.pdf")

    def test_no_images(self, tmp_path: Path) -> None:
        with pytest.raises(PdfInputError, match="at least one"):
            images_to_pdf([], tmp_path / "o.pdf")

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        image = write_noise_png(tmp_path / "a.png")
        out = tmp_path / "album.pdf"
        images_to_pdf([image], out, dry_run=True)
        assert not out.exists()


class TestInfo:
    def test_info_report(self, tmp_path: Path) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 3)
        info = pdf_info(source)
        assert info.pages == 3
        assert info.width_mm == pytest.approx(210.0, abs=0.5)
        assert info.height_mm == pytest.approx(297.0, abs=0.5)
        assert info.title is None

    def test_info_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(PdfInputError, match="not found"):
            pdf_info(tmp_path / "ghost.pdf")


class TestReadPdf:
    def test_encrypted_pdf_refused(self, tmp_path: Path) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        locked = tmp_path / "locked.pdf"
        with locked.open("wb") as handle:
            writer.write(handle)
        with pytest.raises(PdfInputError, match="password-protected"):
            read_pdf(locked)

    def test_unwritable_output_dir(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 1)
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a dir")
        with pytest.raises(PdfOutputError):
            merge_pdfs([first, second], blocker / "out.pdf")
