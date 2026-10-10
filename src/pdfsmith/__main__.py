"""Run pdfsmith as a module: ``python -m pdfsmith merge ...``."""

from __future__ import annotations

from .cli import main

raise SystemExit(main())
