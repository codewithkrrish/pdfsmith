"""Specific exception types for pdfsmith.

Every error carries a human-readable message and the process exit code the
CLI should use. Nothing here leaks tracebacks to end users.
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_USAGE = 2  # argparse's own convention for bad flags
EXIT_INPUT = 3
EXIT_OUTPUT = 4


class PdfsmithError(Exception):
    """Base error; ``str(exc)`` is safe to show to the end user."""

    exit_code = 1


class PdfInputError(PdfsmithError):
    """An input file is missing, unreadable, or invalid."""

    exit_code = EXIT_INPUT


class PdfOutputError(PdfsmithError):
    """An output cannot be written."""

    exit_code = EXIT_OUTPUT
