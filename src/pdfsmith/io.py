"""File I/O helpers: safe PDF reading, atomic writes, collision-safe outputs."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Iterator, Union

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from .errors import PdfInputError, PdfOutputError

PathLike = Union[str, "os.PathLike[str]"]


def read_pdf(path: PathLike) -> PdfReader:
    """Open *path* as a PDF, raising a human-friendly error on any problem.

    Empty-password decryption is attempted once for encrypted files; if the
    file is still locked afterwards, pdfsmith refuses to touch it.
    """
    location = Path(path)
    if not location.exists():
        raise PdfInputError(f"input not found: {location}")
    if not location.is_file():
        raise PdfInputError(f"not a file: {location}")
    try:
        reader = PdfReader(str(location))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfInputError(f"cannot read '{location}': not a valid PDF") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001 - any failure means it stays locked
            pass
        if reader.is_encrypted:
            raise PdfInputError(
                f"'{location}' is password-protected — "
                "decrypt it first (pdfsmith never asks for passwords)"
            )
    return reader


@contextlib.contextmanager
def staged_output(destination: PathLike) -> Iterator[Path]:
    """Yield a temp path; atomically move it to *destination* on success.

    The temp file lives in the destination's directory so the final
    ``os.replace`` is atomic on the same filesystem — a crash mid-write can
    never leave a half-written PDF behind.
    """
    destination = Path(destination)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfOutputError(f"cannot create directory '{destination.parent}': {exc}") from exc
    fd, tmp_name = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=".pdfsmith-",
        suffix=destination.suffix or ".tmp",
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        os.replace(tmp, destination)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_pdf(writer: PdfWriter, destination: PathLike) -> None:
    """Write a ``PdfWriter`` to *destination* atomically."""
    try:
        with staged_output(destination) as tmp:
            with tmp.open("wb") as handle:
                writer.write(handle)
    except PdfOutputError:
        raise
    except OSError as exc:
        raise PdfOutputError(f"cannot write '{destination}': {exc}") from exc


def plan_output(path: PathLike, *, force: bool) -> Path:
    """Decide the real output path for *path*.

    Never overwrites silently: unless *force* is set, an existing file is
    preserved and a numbered sibling (``name-2.pdf``, ``name-3.pdf``, ...)
    is returned instead.
    """
    candidate = Path(path)
    if force or not candidate.exists():
        return candidate
    number = 2
    while True:
        numbered = candidate.with_name(f"{candidate.stem}-{number}{candidate.suffix}")
        if not numbered.exists():
            return numbered
        number += 1
