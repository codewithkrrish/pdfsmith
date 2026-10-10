"""Tests for CLI wiring: exit codes, dry-run output, error translation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfsmith.cli import main
from pdfsmith.errors import EXIT_INPUT, EXIT_OK, EXIT_OUTPUT, EXIT_USAGE

from conftest import write_blank_pdf


def run_cli(*argv: str) -> int:
    return main(list(argv))


class TestExitCodes:
    def test_info_ok(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 2)
        assert run_cli("info", str(source)) == EXIT_OK
        assert "pages:     2" in capsys.readouterr().out

    def test_missing_input_is_exit_3(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        assert run_cli("merge", str(tmp_path / "ghost.pdf"), str(tmp_path / "b.pdf"),
                        "-o", str(tmp_path / "out.pdf")) == EXIT_INPUT
        assert "pdfsmith: error:" in capsys.readouterr().err

    def test_bad_flag_is_exit_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_cli("merge", "--nope")
        assert exc.value.code == EXIT_USAGE

    def test_missing_required_flag_is_exit_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            run_cli("merge", "a.pdf")
        assert exc.value.code == EXIT_USAGE

    def test_unwritable_output_is_exit_4(self, tmp_path: Path) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 1)
        blocker = tmp_path / "blocker"
        blocker.write_text("file, not dir")
        assert run_cli("merge", str(first), str(second),
                        "-o", str(blocker / "out.pdf")) == EXIT_OUTPUT

    def test_no_traceback_on_user_errors(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        run_cli("info", str(tmp_path / "ghost.pdf"))
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert err.startswith("pdfsmith: error:")


class TestDryRun:
    def test_merge_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        first = write_blank_pdf(tmp_path / "a.pdf", 1)
        second = write_blank_pdf(tmp_path / "b.pdf", 2)
        out = tmp_path / "merged.pdf"
        assert run_cli("merge", str(first), str(second), "-o", str(out), "--dry-run") == EXIT_OK
        assert "would merge 2 files (3 pages)" in capsys.readouterr().out
        assert not out.exists()

    def test_compress_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 1)
        out = tmp_path / "small.pdf"
        assert run_cli("compress", str(source), "-o", str(out),
                        "--level", "2", "--dry-run") == EXIT_OK
        assert "would compress" in capsys.readouterr().out
        assert not out.exists()

    def test_split_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        source = write_blank_pdf(tmp_path / "doc.pdf", 3)
        assert run_cli("split", str(source), "-o", str(tmp_path / "parts"),
                        "--dry-run") == EXIT_OK
        assert "would split" in capsys.readouterr().out
        assert not (tmp_path / "parts").exists()


class TestVersion:
    def test_version_flag(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit) as exc:
            run_cli("--version")
        assert exc.value.code == 0
        assert "pdfsmith" in capsys.readouterr().out
