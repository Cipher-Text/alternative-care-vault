# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A personal reference collection of alternative-medicine books (homeopathy, Ayurveda, Unani, plus a `general` bucket for cross-disciplinary works), plus a Python pipeline that turns the raw source files into a clean, searchable local database. There is no application code to build/lint/test — the only "code" is the two scripts in `tools/` (`process_book.py`, `build_library_db.py`); `catalogue_seed.json` there is hand-maintained metadata, not code.

**Copyright note:** almost every book here is an older work with a plausible (if unverified) public-domain argument. Nine are not: four in `raw/general/` -- `Marc S. Micozzi - Fundamentals of Complementary and Alternative Medicine - 5th Edition.epub` (2014 Elsevier textbook), `Edzard Ernst et al. - Oxford Handbook of Complementary Medicine.epub` (Oxford University Press handbook, likely from an Archive.org Controlled Digital Lending scan — a lending-restriction bypass, not just an ambiguous-vintage work), `Michael Heinrich et al. - Fundamentals of Pharmacognosy and Phytotherapy - 4th Edition.epub` (Elsevier VitalSource retail textbook with a leftover Adobe ADEPT DRM tag proving it was stripped from a purchased copy), and `Joanne Barnes et al. - Herbal Medicines - 3rd Edition.epub` (2007 Pharmaceutical Press reference text, downloaded from a third-party site rather than any ambiguous-vintage archive) -- two in `raw/unani/`: `DGHS - The Unani Pharmacopia of Bangladesh - Part 1 Volume 4 (2020).pdf` (a 2020 Government of Bangladesh publication with its own explicit ownership/copyright line in the front matter; unlike US federal works, Bangladeshi government publications are not automatically public domain) and `AYUSH - National Formulary of Unani Medicine - Part 2 Volume 1 (2007).pdf` (a 2007 Government of India/AYUSH publication, ISBN 81-87748-02-8 -- no explicit rights-reserved notice found, but still a modern government-owned work under Indian copyright law) -- and three in `raw/ayurveda/`: `Oushadhi - Therapeutic Index - 5th Impression (2019).pdf` (a 2019 publication from a Government of Kerala state undertaking, carrying the collection's most explicit copyright statement: "Copy right reserved. No part of this publication may be translated or transmitted...without permission"), `Bhavamishra - Bhavaprakasha Vol 1 (with Nighantu) - Trans. K.R. Srikantha Murthy - 2001.epub` (a 2001 Krishnadas Academy translation, added to fill the "Laghu Trayi" materia-medica/nighantu gap alongside the homeopathy repertories), and `Madhavakara - Madhava Nidana (Ayurvedic Diagnostics) Vol 1 - Trans. Kanjiv Lochan, ed. Brahmanand Tripathi.epub` (a modern Chaukhamba Surbharati Prakashan translation, Volume I of II only -- the fuller work runs 79 chapters and no complete English edition was found). All nine were added at the user's explicit request after being flagged as copyright concerns — each time asked and confirmed separately, not as a standing blanket approval. Don't treat this as precedent for adding other modern copyrighted works without the same explicit, informed confirmation — and think carefully before this repo is ever pushed somewhere public while these files remain in `raw/`.

**Unresolved gap in this flagging process:** `ashtanga-hridaya-vagbhatta-vol-1` (English translation of the Ashtanga Hridaya, Vol. I, translator Srikantha Murthy K.R.) is the same translator/publisher-family era as the Bhavaprakasha entry above but was added earlier and was never run through this copyright-flagging process -- it carries no year, no copyright note, and isn't listed among the nine exceptions. It should be treated as carrying the same unresolved modern-copyright concern rather than as evidence this category of work is safe; it just hasn't been explicitly confirmed with the user yet.

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
- Four sources are raw PDFs handled by a separate `parse_source_pdf()` path using `pypdf`'s per-page text layer, with no EPUB conversion involved: `Samuel Hahnemann - Organon of Medicine.pdf`, `DGHS - The Unani Pharmacopia of Bangladesh - Part 1 Volume 4 (2020).pdf`, `AYUSH - National Formulary of Unani Medicine - Part 2 Volume 1 (2007).pdf`, and `Oushadhi - Therapeutic Index - 5th Impression (2019).pdf`. Page numbers there are raw PDF page indices, not printed folio numbers (though for the three government-formulary PDFs the index happens to line up with each page's own printed footer number). These are distinct from the `raw/general/` books below, whose source PDFs were converted to EPUB *before* being placed in `raw/` rather than kept as PDFs.
- `micozzi-fundamentals-of-complementary-and-alternative-medicine-5th` and `ernst-oxford-handbook-of-complementary-medicine` aren't from Internet Archive at all — the user supplied PDFs (the Micozzi one born-digital with real text/TOC/images; the Ernst one an Internet-Archive-OCR'd scan with a real text layer but no embedded TOC and ~900 JPEG2000 images, which aren't a valid EPUB format and were dropped as likely OCR artifacts) that were each converted to EPUB with the same one-off script (not part of this repo) mimicking the standard `<title>Page N</title>` + one-`<p>`-per-page layout, specifically so they'd pass through the *ordinary* `parse_source_epub()` path unmodified. That conversion script no longer exists anywhere in this repo; if either book ever needs reprocessing from its original PDF, it must be rebuilt (page text + TOC + images) from scratch, since only page text survived into `raw/general/`'s EPUBs and then into `processed/`.
- `heinrich-fundamentals-of-pharmacognosy-and-phytotherapy-4th` is a different case again: a genuine Elsevier retail EPUB with real EPUB3 semantic structure (`epub:type="pagebreak"` spans carrying the actual printed page number as `aria-label`, including roman numerals for front matter; `<h1 class="chaptitle">` for real chapter headings) but body text inside `<div>` elements, not `<p>` tags. Critically, the *ordinary* `parse_source_epub()` does **not** cleanly fail on it — it silently extracts ~26 garbage pseudo-pages from incidental `<p>` tags elsewhere in the file (marketing boilerplate, duplicated TOC fragments, all with `page_number: None`), which is enough to pass the "no pages extracted" check and would silently overwrite the correct `processed/` output with garbage. This is why `REQUIRES_DEDICATED_SCRIPT` in `process_book.py` explicitly skips this id in both `--all` and single-id mode with a clear message, rather than letting it fall through to the generic parser. It was actually processed with a second one-off script (also not in this repo) that walks the real pagebreak/chapter markup directly and calls this file's own `build_book_json()`/`build_epub()` — meaning its `page_number` values and `chapters[]` array are the actual book's real pagination/TOC, meaningfully higher fidelity than every other book's guessed/regex-derived structure. If this book ever needs reprocessing, that script must be rebuilt first; don't remove it from `REQUIRES_DEDICATED_SCRIPT` without one ready.
- A few sources (currently two Bengali facsimiles: `idris-ali-bissoykor-lokkhone-homoeopathic-chikitsa`, `pandey-homoeopathic-practice-of-medicine`) have **no text layer at all** — every page is only a scanned image. These are marked `"source_format": "facsimile-epub"` in `catalogue_seed.json` and routed to `parse_source_facsimile_epub()`, which shells out to the `tesseract` CLI per page image using the entry's `"ocr_lang"` (`ben+eng` for both — plain `ben` badly mis-recognizes embedded Latin homeopathic remedy names, e.g. "Glonion 1x" read as garbage digits). This requires `tesseract` and the relevant `.traineddata` installed locally (not in `tools/requirements.txt`, since it's a system binary, not a pip package) — see the README's "Processed versions" section. OCR quality here is a genuine new artifact (errors introduced by this pipeline), unlike every other book's OCR (already present in the source, just cleaned up) — don't conflate the two when reasoning about text quality. New facsimile sources follow the same pattern: move/rename into `raw/`, add a catalogue entry with `source_format`/`ocr_lang` set, run `process_book.py <id>` (budget real time — Tesseract runs at roughly 1-1.5s/page, so a few-hundred-page book takes several minutes; run it in the background rather than blocking on it).
- OCR cleanup is intentionally light-touch: Unicode NFKC normalization and whitespace collapsing only. Garbled OCR (e.g. "CHAR AKA samhitA" for "CHARAKA SAMHITA") is left as-is by design — re-OCRing from page images was explicitly deferred, not overlooked.
- Rebuilt EPUBs preserve pagination via a `<span id="page-N">`/`<p class="pagenum">` anchor at each original page boundary. Chapter/heading-level TOC detection is *not* attempted generically — the source OCR has zero heading markup (no `<h1>`-`<h6>` anywhere) — but `CHAPTER_PATTERNS` in `process_book.py` adds book-specific chapter extraction for two books where a reliable canonical opening phrase exists in the OCR text itself:
  - `charaka-samhita-kaviratna-1892`: `LESSON <roman>. And now we shall expound the Lesson called/on <title>` (and phrasing variants)
  - `sushruta-samhita-vol-2-1911`: `CHAPTER <roman>. Now we shall discourse on <title>`
  These patterns were reverse-engineered from the actual OCR text and deliberately require the full opening phrase, not just the bare "LESSON N"/"CHAPTER N" token, because both books also mention chapter numbers in table-of-contents pages and footnote cross-references that must NOT be treated as chapter starts. Detected chapters land in `book.json`'s `chapters` array and the EPUB's `nav.xhtml`. Coverage is best-effort (OCR noise causes some real lessons/chapters to be missed) — do not treat the list as exhaustive.
  - The **Bengali** Charaka Samhita edition (`charaka-samhita-satish-chandra-sharma-bengali`) was investigated too but deliberately excluded: its chapter markers ("N অধ্যায়") suffer heavy OCR numeral corruption (e.g. ২ misread as ই), making reliable ordinal parsing impractical without a from-scratch Bengali OCR-correction effort. Revisit only if that book's OCR quality improves (e.g. via re-OCR).
  - No other book among the original 15 has any chapter/section structure in its OCR text at all (verified by scanning all 15 for `CHAPTER`/`LESSON`/`PART`/`SECTION`/Bengali equivalents) — most are alphabetical materia medica/repertory references with no narrative chapters to begin with. The two later-added Bengali facsimile books (`idris-ali-bissoykor-lokkhone-homoeopathic-chikitsa`, `pandey-homoeopathic-practice-of-medicine`) have a handful of Bengali chapter-word occurrences (অধ্যায়/পরিচ্ছেদ/খণ্ড — 6 and 24 respectively) that have *not* been investigated for real structure; given the low counts and this collection's precedent (low counts elsewhere turned out to be incidental mentions, not real chapters), don't assume either way without checking first.

## Known gaps (deferred, not bugs)

- `raw/unani/Ibn Sina - The Canon of Medicine.epub` is a 0-byte placeholder and is intentionally excluded from `tools/catalogue_seed.json` until a real file replaces it.

## Important: `raw/` is not 100% mirrored into git

`raw/ayurveda/Charaka Samhita - English Translation by Abinash Chandra Kaviratna - 1892.epub` (~1GB) is **gitignored**, not tracked. It was committed early on, which pushed `.git` past GitHub's 100MB-per-file hard limit and made every push fail; on 2026-09-22 it was stripped out of all git history with `git filter-repo` (rewriting every commit hash) and the working-tree copy was restored afterward, gitignored to prevent recommitting it. The file still exists locally in `raw/ayurveda/` for reprocessing, it's just not versioned. Its clean 5MB derivative (which *is* tracked) lives at `processed/ayurveda/charaka-samhita-kaviratna-1892/`. If this repo is ever re-cloned, that one raw file will be missing and `process_book.py` can't regenerate its `processed/` output without it being placed back manually.
