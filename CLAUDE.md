# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A personal reference collection of alternative-medicine books (homeopathy, Ayurveda, Unani), plus a Python pipeline that turns the raw source files into a clean, searchable local database. There is no application code to build/lint/test — the only "code" is the three scripts in `tools/`.

## Data flow

```
raw/<discipline>/<file>.epub|.pdf   (original, untouched, as-downloaded)
        |  tools/process_book.py
        v
processed/<discipline>/<book-id>/{book.epub, book.json}   (clean text, page-anchored)
processed/catalogue.json                                  (aggregated metadata index)
        |  tools/build_library_db.py
        v
db/library.db   (SQLite, FTS5 full-text search — git-ignored, regenerable build artifact)
```

`raw/` is source of truth and is never edited in place. Everything downstream is derived and can be regenerated at any time by rerunning the two scripts below.

## Commands

```sh
pip3 install -r tools/requirements.txt      # pypdf, for PDF sources

python3 tools/process_book.py --all         # regenerate processed/ for every catalogued book
python3 tools/process_book.py <book-id>     # regenerate a single book (id = key in tools/catalogue_seed.json)

python3 tools/build_library_db.py           # rebuild db/library.db from processed/catalogue.json
```

Query example (full-text search over page text):

```sh
sqlite3 db/library.db "
  SELECT b.title, p.page_number, snippet(pages_fts, 0, '[', ']', '...', 12)
  FROM pages_fts
  JOIN pages p ON p.id = pages_fts.rowid
  JOIN books b ON b.id = p.book_id
  WHERE pages_fts MATCH 'aconite'
  ORDER BY rank LIMIT 5;
"
```

## Adding a new book

1. Place the original file under `raw/<discipline>/` using `Author - Title - Edition.ext`.
2. Add a matching entry to `tools/catalogue_seed.json` (`id`, `discipline`, `raw_file`, `title`, `author`, `year`, `language`, etc.). **Metadata must be filled in by hand** — the source EPUBs/PDFs carry no usable `dc:title`/`dc:creator` (Internet Archive exports only embed a random UUID and accessibility boilerplate), so `process_book.py` has nothing to read metadata from.
3. Add the book to the collection table in `README.md`.
4. Rerun `process_book.py --all` (or the single id) and then `build_library_db.py`.

## Source file quirks (`tools/process_book.py`)

- Source EPUBs are Internet Archive OCR exports: one XHTML file per original page (page number recoverable from the `<title>` tag), one `<p>` of OCR'd text per page. Some also embed a full-resolution JPEG scan of every page — `process_book.py` reads only the `<p>` text and never copies these images into `processed/`, since that's what made the raw Charaka Samhita EPUB ~1GB. Do not add image-preservation logic without discussing the size tradeoff first.
- The one PDF source (`Samuel Hahnemann - Organon of Medicine.pdf`) is handled by a separate `parse_source_pdf()` path using `pypdf`'s per-page text layer; page numbers there are raw PDF page indices, not printed folio numbers.
- OCR cleanup is intentionally light-touch: Unicode NFKC normalization and whitespace collapsing only. Garbled OCR (e.g. "CHAR AKA samhitA" for "CHARAKA SAMHITA") is left as-is by design — re-OCRing from page images was explicitly deferred, not overlooked.
- Rebuilt EPUBs preserve pagination via a `<span id="page-N">`/`<p class="pagenum">` anchor at each original page boundary, but do not attempt chapter/heading-level TOC detection — `nav.xhtml` only links the first page.

## Known gaps (deferred, not bugs)

- `raw/unani/Ibn Sina - The Canon of Medicine.epub` is a 0-byte placeholder and is intentionally excluded from `tools/catalogue_seed.json` until a real file replaces it.
- `.git` history still contains the original ~1GB Charaka Samhita blob from before the cleanup pipeline existed; this was left alone deliberately rather than rewriting history.
