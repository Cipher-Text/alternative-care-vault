# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A personal reference collection of alternative-medicine books (homeopathy, Ayurveda, Unani), plus a Python pipeline that turns the raw source files into a clean, searchable local database. There is no application code to build/lint/test — the only "code" is the two scripts in `tools/` (`process_book.py`, `build_library_db.py`); `catalogue_seed.json` there is hand-maintained metadata, not code.

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
2. Add a matching entry to `tools/catalogue_seed.json` (`id`, `discipline`, `raw_file`, `title`, `author`, `year`, `language`, etc.). **Metadata must be filled in by hand** — the source EPUBs/PDFs carry no usable `dc:title`/`dc:creator` (Internet Archive exports only embed a random UUID and accessibility boilerplate), so `process_book.py` has nothing to read metadata from. If the source is a pure page-scan with no text layer at all, also set `"source_format": "facsimile-epub"` and `"ocr_lang"` (a `tesseract` language code) — see "Source file quirks" below.
3. Add the book to the collection table in `README.md`.
4. Rerun `process_book.py --all` (or the single id) and then `build_library_db.py`.

## Source file quirks (`tools/process_book.py`)

- Source EPUBs are Internet Archive OCR exports: one XHTML file per original page (page number recoverable from the `<title>` tag), one `<p>` of OCR'd text per page. Some also embed a full-resolution JPEG scan of every page — `process_book.py` reads only the `<p>` text and never copies these images into `processed/`, since that's what made the raw Charaka Samhita EPUB ~1GB. Do not add image-preservation logic without discussing the size tradeoff first.
- The one PDF source (`Samuel Hahnemann - Organon of Medicine.pdf`) is handled by a separate `parse_source_pdf()` path using `pypdf`'s per-page text layer; page numbers there are raw PDF page indices, not printed folio numbers.
- A few sources (currently two Bengali facsimiles: `idris-ali-bissoykor-lokkhone-homoeopathic-chikitsa`, `pandey-homoeopathic-practice-of-medicine`) have **no text layer at all** — every page is only a scanned image. These are marked `"source_format": "facsimile-epub"` in `catalogue_seed.json` and routed to `parse_source_facsimile_epub()`, which shells out to the `tesseract` CLI per page image using the entry's `"ocr_lang"` (`ben+eng` for both — plain `ben` badly mis-recognizes embedded Latin homeopathic remedy names, e.g. "Glonion 1x" read as garbage digits). This requires `tesseract` and the relevant `.traineddata` installed locally (not in `tools/requirements.txt`, since it's a system binary, not a pip package) — see the README's "Processed versions" section. OCR quality here is a genuine new artifact (errors introduced by this pipeline), unlike every other book's OCR (already present in the source, just cleaned up) — don't conflate the two when reasoning about text quality. New facsimile sources follow the same pattern: move/rename into `raw/`, add a catalogue entry with `source_format`/`ocr_lang` set, run `process_book.py <id>` (budget real time — Tesseract runs at roughly 1-1.5s/page, so a few-hundred-page book takes several minutes; run it in the background rather than blocking on it).
- OCR cleanup is intentionally light-touch: Unicode NFKC normalization and whitespace collapsing only. Garbled OCR (e.g. "CHAR AKA samhitA" for "CHARAKA SAMHITA") is left as-is by design — re-OCRing from page images was explicitly deferred, not overlooked.
- Rebuilt EPUBs preserve pagination via a `<span id="page-N">`/`<p class="pagenum">` anchor at each original page boundary. Chapter/heading-level TOC detection is *not* attempted generically — the source OCR has zero heading markup (no `<h1>`-`<h6>` anywhere) — but `CHAPTER_PATTERNS` in `process_book.py` adds book-specific chapter extraction for two books where a reliable canonical opening phrase exists in the OCR text itself:
  - `charaka-samhita-kaviratna-1892`: `LESSON <roman>. And now we shall expound the Lesson called/on <title>` (and phrasing variants)
  - `sushruta-samhita-vol-2-1911`: `CHAPTER <roman>. Now we shall discourse on <title>`
  These patterns were reverse-engineered from the actual OCR text and deliberately require the full opening phrase, not just the bare "LESSON N"/"CHAPTER N" token, because both books also mention chapter numbers in table-of-contents pages and footnote cross-references that must NOT be treated as chapter starts. Detected chapters land in `book.json`'s `chapters` array and the EPUB's `nav.xhtml`. Coverage is best-effort (OCR noise causes some real lessons/chapters to be missed) — do not treat the list as exhaustive.
  - The **Bengali** Charaka Samhita edition (`charaka-samhita-satish-chandra-sharma-bengali`) was investigated too but deliberately excluded: its chapter markers ("N অধ্যায়") suffer heavy OCR numeral corruption (e.g. ২ misread as ই), making reliable ordinal parsing impractical without a from-scratch Bengali OCR-correction effort. Revisit only if that book's OCR quality improves (e.g. via re-OCR).
  - No other book in the collection has any chapter/section structure in its OCR text at all (verified by scanning all 15 for `CHAPTER`/`LESSON`/`PART`/`SECTION`/Bengali equivalents) — most are alphabetical materia medica/repertory references with no narrative chapters to begin with.

## Known gaps (deferred, not bugs)

- `raw/unani/Ibn Sina - The Canon of Medicine.epub` is a 0-byte placeholder and is intentionally excluded from `tools/catalogue_seed.json` until a real file replaces it.

## Important: `raw/` is not 100% mirrored into git

`raw/ayurveda/Charaka Samhita - English Translation by Abinash Chandra Kaviratna - 1892.epub` (~1GB) is **gitignored**, not tracked. It was committed early on, which pushed `.git` past GitHub's 100MB-per-file hard limit and made every push fail; on 2026-09-22 it was stripped out of all git history with `git filter-repo` (rewriting every commit hash) and the working-tree copy was restored afterward, gitignored to prevent recommitting it. The file still exists locally in `raw/ayurveda/` for reprocessing, it's just not versioned. Its clean 5MB derivative (which *is* tracked) lives at `processed/ayurveda/charaka-samhita-kaviratna-1892/`. If this repo is ever re-cloned, that one raw file will be missing and `process_book.py` can't regenerate its `processed/` output without it being placed back manually.
