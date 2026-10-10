# pdfsmith

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

A Swiss-army CLI for everyday PDF chores: **merge**, **split**, **compress**,
and **images-to-PDF**. Everything runs locally on your machine — no uploads,
no watermarks, no page limits, no accounts.

## Why

Online PDF tools make you upload private documents to someone else's server and
throttle you after a few files. pdfsmith does the four jobs people actually
need, from the terminal, in one dependency-light package:

```console
$ pdfsmith merge ch1.pdf ch2.pdf -o book.pdf --title "My Book"
merged 2 files (5 pages) -> book.pdf

$ pdfsmith split book.pdf -o parts --ranges "1-3,5"
split book.pdf into 2 files:
  parts/book-1.pdf
  parts/book-2.pdf

$ pdfsmith images scan1.png scan2.png -o scans.pdf --page-size a4
wrote 2 images (a4 pages) -> scans.pdf

$ pdfsmith compress scans.pdf -o scans-small.pdf --level 2 --dpi 100
compressed 1.7 MB -> 663.7 KB (saved 63%) -> scans-small.pdf [2 images downscaled]

$ pdfsmith info book.pdf
path:      book.pdf
pages:     5
page size: 210.0 x 297.0 mm
title:     My Book
author:    -
images:    0
```

## Install

Requires Python 3.9+.

```console
pip install git+https://github.com/codewithkrrish/pdfsmith.git
```

Or with [pipx](https://pipx.pypa.io/) for an isolated install:

```console
pipx install git+https://github.com/codewithkrrish/pdfsmith.git
```

## Usage

```
pdfsmith merge PDF [PDF ...] -o OUT [--title TITLE]
pdfsmith split PDF [-o DIR] [--ranges "1-3,5,8-"] [--prefix NAME]
pdfsmith compress PDF -o OUT [--level 1|2] [--dpi DPI]
pdfsmith images IMAGE [IMAGE ...] -o OUT [--page-size fit|a4]
pdfsmith info PDF
```

Every write command accepts `--force` (overwrite instead of auto-rename) and
`--dry-run` (print what would happen, write nothing).

### merge

Concatenate PDFs in the order given. `--title` sets the document title metadata.

### split

Split into several files. `--ranges` uses 1-based pages, e.g. `"1-3,5,8-"`
(a trailing dash means "to the last page"). Without `--ranges`, you get one
file per page. Outputs are named `<prefix>-<n>.pdf`.

### compress

- `--level 1` (default): lossless — recompresses content streams and merges
  duplicate objects.
- `--level 2`: also downscales raster images that render above `--dpi`
  (default 150). This is where scanned PDFs shrink dramatically.

### images

One image per page. `--page-size fit` sizes each page to its image;
`--page-size a4` fits every image onto a true A4 page (210 x 297 mm),
preserving aspect ratio on a white canvas.

### info

Page count, page size, title/author metadata, and embedded image count.

### Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | success |
| 2 | bad flags / usage error |
| 3 | input problem (missing, corrupt, or password-protected file) |
| 4 | output problem (cannot write) |

### Safety

- **Never overwrites silently.** If the output exists, pdfsmith writes
  `name-2.pdf`, `name-3.pdf`, ... unless you pass `--force`.
- **Atomic writes.** Outputs are written to a temp file and renamed into
  place, so an interrupted run can never leave a half-written PDF.
- **Password-protected PDFs are refused** with a clear message — pdfsmith
  never asks for passwords.
- **Destructive mistakes are previewable** with `--dry-run`.

## Project structure

```
src/pdfsmith/
    cli.py      argparse wiring only; maps errors to exit codes
    ops.py      merge / split / compress / images / info (testable, no I/O printing)
    ranges.py   "1-3,5,8-" page-range parsing
    io.py       safe PDF reading, atomic writes, collision-safe output names
    errors.py   specific exception types with human messages
tests/          pytest suite (happy path + edge cases)
```

## License

MIT — see [LICENSE](LICENSE).

Built by [Krrish](https://github.com/codewithkrrish).
