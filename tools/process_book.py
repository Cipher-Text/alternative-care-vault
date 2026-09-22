#!/usr/bin/env python3
"""
Rebuild a clean, text-only EPUB + page-mapped JSON from a raw Internet-Archive-style
source EPUB (one XHTML file per scanned page, dirty OCR text, no real metadata).

Usage:
    python3 process_book.py <catalogue_id> [--catalogue tools/catalogue_seed.json]
                                            [--raw-root raw] [--out-root processed]
    python3 process_book.py --all
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pypdf

NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"

PAGE_TITLE_RE = re.compile(r"(\d+)")

# Book-specific chapter-opening patterns. These are deliberately narrow (matched against
# each translation's own canonical opening phrasing) so they catch real chapter/lesson
# starts while skipping table-of-contents listings and footnote cross-references, which
# mention the same "LESSON N" / "CHAPTER N" tokens without the opening phrase.
# Group 1 = chapter/lesson number label, group 2 = a short title guess (best-effort, may
# retain OCR noise). Only added where this was verified against the actual source text;
# see tools/catalogue_seed.json / CLAUDE.md for which books have this and why others don't.
CHAPTER_PATTERNS = {
    "charaka-samhita-kaviratna-1892": (
        "Lesson",
        re.compile(
            r"LESSON\s+([IVXLC]+)[.:]?\s*"
            r"(?:We (?:shall|will)|And now we shall|So then We will)[^.\n]{0,40}?"
            r"(?:expound|explain)\s+(?:the\s+)?[Ll]esson\s*"
            r"(?:called|on|having for its topic|about)?\s*[‘’'\"“”]?([^.\n]{2,90})",
            re.IGNORECASE,
        ),
    ),
    "sushruta-samhita-vol-2-1911": (
        "Chapter",
        re.compile(
            r"CHAPTER\s+([IVXLC]+)\.?\s+Now (?:we|wc) shall discourse on\s+(?:the\s+)?([^.\n]{2,100})",
            re.IGNORECASE,
        ),
    ),
}


def detect_chapters(book_id, pages):
    """Best-effort chapter/lesson list for the few books with a known-reliable pattern.
    Returns [] for every other book -- see CHAPTER_PATTERNS docstring above."""
    spec = CHAPTER_PATTERNS.get(book_id)
    if not spec:
        return []
    label_word, pattern = spec

    chapters = []
    for p in pages:
        for m in pattern.finditer(p["text"]):
            chapters.append(
                {
                    "label": f"{label_word} {m.group(1).upper()}",
                    "title": m.group(2).strip(" .,-"),
                    "start_page": p["page_number"],
                }
            )
    return chapters


def clean_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")  # soft hyphen artifacts
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def parse_source_epub(epub_path):
    """Returns list of {"page_number": int|None, "label": str, "text": str} in spine order."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(tmp)

        container = ET.parse(tmp / "META-INF/container.xml")
        rootfile = container.find(
            ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
        ).get("full-path")
        opf_path = tmp / rootfile
        opf_dir = opf_path.parent

        opf = ET.parse(opf_path)
        manifest = {
            item.get("id"): item.get("href")
            for item in opf.findall(f".//{{{NS_OPF}}}manifest/{{{NS_OPF}}}item")
        }
        media_types = {
            item.get("id"): item.get("media-type")
            for item in opf.findall(f".//{{{NS_OPF}}}manifest/{{{NS_OPF}}}item")
        }
        spine = [
            itemref.get("idref")
            for itemref in opf.findall(f".//{{{NS_OPF}}}spine/{{{NS_OPF}}}itemref")
        ]

        pages = []
        for idref in spine:
            href = manifest.get(idref)
            if not href or media_types.get(idref) not in (
                "application/xhtml+xml",
                "text/html",
            ):
                continue
            page_file = opf_dir / href
            if not page_file.exists():
                continue

            html = page_file.read_text(encoding="utf-8")
            try:
                root = ET.fromstring(html.encode("utf-8"))
            except ET.ParseError:
                continue

            title_el = root.find(f".//{{{NS_XHTML}}}title")
            label = (title_el.text or "").strip() if title_el is not None else ""
            m = PAGE_TITLE_RE.search(label)
            page_number = int(m.group(1)) if m else None

            paragraphs = root.findall(f".//{{{NS_XHTML}}}p")
            text = "\n\n".join(
                "".join(p.itertext()) for p in paragraphs if "".join(p.itertext()).strip()
            )
            text = clean_text(text)

            if not text and page_number is None:
                continue  # skip cover/nav/structural pages with nothing to keep

            pages.append({"page_number": page_number, "label": label, "text": text})

        return pages


def parse_source_facsimile_epub(epub_path, ocr_lang):
    """For EPUBs with no text layer at all -- every page is just a scanned page image.
    Runs Tesseract OCR (requires the `tesseract` binary + the given language data
    installed, e.g. `brew install tesseract` + ben.traineddata) over each page image in
    spine/manifest order. Returns list of {"page_number": int, "label": str, "text": str}."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(tmp)

        container = ET.parse(tmp / "META-INF/container.xml")
        rootfile = container.find(
            ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
        ).get("full-path")
        opf_path = tmp / rootfile
        opf_dir = opf_path.parent

        opf = ET.parse(opf_path)
        items = opf.findall(f".//{{{NS_OPF}}}manifest/{{{NS_OPF}}}item")
        image_hrefs = sorted(
            (item.get("href") for item in items if (item.get("media-type") or "").startswith("image/")),
        )

        pages = []
        for i, href in enumerate(image_hrefs, start=1):
            image_path = opf_dir / href
            if not image_path.exists():
                continue
            result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", ocr_lang],
                capture_output=True, text=True,
            )
            text = clean_text(result.stdout)
            pages.append({"page_number": i, "label": f"Page {i}", "text": text})
            print(f"  OCR page {i}/{len(image_hrefs)}\r", end="", flush=True)
        print()
        return pages


def parse_source_pdf(pdf_path):
    """Returns list of {"page_number": int, "label": str, "text": str}, one per PDF page."""
    reader = pypdf.PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        if not text:
            continue  # blank/cover/image-only page with no extractable text layer
        pages.append({"page_number": i, "label": f"Page {i}", "text": text})
    return pages


def build_book_json(meta, pages, chapters, out_path):
    doc = {
        "id": meta["id"],
        "title": meta["title"],
        "author": meta.get("author"),
        "editor": meta.get("editor"),
        "translator": meta.get("translator"),
        "year": meta.get("year"),
        "edition": meta.get("edition"),
        "volume": meta.get("volume"),
        "language": meta.get("language"),
        "discipline": meta["discipline"],
        "source_raw_file": meta["raw_file"],
        "note": meta.get("note"),
        "page_count": len(pages),
        "chapters": chapters,
        "pages": pages,
    }
    doc = {k: v for k, v in doc.items() if v not in (None, [])}
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def esc(s):
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_epub(meta, pages, chapters, out_path):
    book_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"alternative-care-vault:{meta['id']}"))
    title = meta["title"]
    author = meta.get("author") or meta.get("translator") or "Unknown"
    language = meta.get("language", "en")

    manifest_items = []
    spine_items = []
    page_files = []
    fname_by_page_number = {}

    for i, page in enumerate(pages, start=1):
        fname = f"page_{i:04d}.xhtml"
        if page["page_number"] is not None:
            fname_by_page_number.setdefault(page["page_number"], fname)
        anchor_id = (
            f"page-{page['page_number']}" if page["page_number"] is not None else f"leaf-{i}"
        )
        label = esc(page["label"] or f"Page {page['page_number'] or i}")
        body_paras = "\n    ".join(
            f"<p>{esc(para)}</p>" for para in page["text"].split("\n\n") if para.strip()
        )
        xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{language}">
  <head>
    <title>{label}</title>
    <link href="style.css" rel="stylesheet" type="text/css"/>
  </head>
  <body>
    <p class="pagenum" id="{anchor_id}">{label}</p>
    {body_paras}
  </body>
</html>"""
        page_files.append((fname, xhtml))
        manifest_items.append(f'<item id="p{i}" href="{fname}" media-type="application/xhtml+xml"/>')
        spine_items.append(f'<itemref idref="p{i}"/>')

    if chapters:
        chapter_links = "\n        ".join(
            f'<li><a href="{fname_by_page_number.get(c["start_page"], page_files[0][0])}">'
            f'{esc(c["label"])}{esc(" — " + c["title"] if c.get("title") else "")}</a></li>'
            for c in chapters
        )
    else:
        chapter_links = f'<li><a href="{page_files[0][0]}">Start of book</a></li>'

    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{language}">
  <head><title>Table of Contents</title></head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>{esc(title)}</h1>
      <ol>
        {chapter_links}
      </ol>
    </nav>
  </body>
</html>"""

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{esc(title)}</dc:title>
    <dc:creator>{esc(author)}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:source>{esc(meta['raw_file'])}</dc:source>
    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="style" href="style.css" media-type="text/css"/>
    {chr(10).join('    ' + m for m in manifest_items)}
  </manifest>
  <spine>
    <itemref idref="nav" linear="no"/>
    {chr(10).join('    ' + s for s in spine_items)}
  </spine>
</package>"""

    css = """body { font-family: serif; line-height: 1.5; margin: 1em; }
.pagenum { text-align: center; font-size: 0.75em; color: #888; margin: 1.5em 0 0.5em; }
"""

    container_xml = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile media-type="application/oebps-package+xml" full-path="EPUB/content.opf"/>
  </rootfiles>
</container>"""

    if out_path.exists():
        out_path.unlink()
    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/content.opf", opf)
        zf.writestr("EPUB/nav.xhtml", nav_xhtml)
        zf.writestr("EPUB/style.css", css)
        for fname, xhtml in page_files:
            zf.writestr(f"EPUB/{fname}", xhtml)


def process_one(meta, raw_root, out_root):
    raw_path = raw_root / meta["raw_file"]
    if not raw_path.exists():
        print(f"SKIP (missing source): {raw_path}")
        return

    print(f"Processing {meta['id']} ...")
    if meta.get("source_format") == "facsimile-epub":
        pages = parse_source_facsimile_epub(raw_path, meta.get("ocr_lang", "eng"))
    elif raw_path.suffix.lower() == ".pdf":
        pages = parse_source_pdf(raw_path)
    else:
        pages = parse_source_epub(raw_path)
    if not pages:
        print(f"  WARNING: no pages extracted for {meta['id']}")
        return

    chapters = detect_chapters(meta["id"], pages)

    out_dir = out_root / meta["discipline"] / meta["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    build_book_json(meta, pages, chapters, out_dir / "book.json")
    build_epub(meta, pages, chapters, out_dir / "book.epub")

    src_size = raw_path.stat().st_size
    out_size = (out_dir / "book.epub").stat().st_size
    chapter_note = f", {len(chapters)} chapters detected" if chapters else ""
    print(
        f"  {len(pages)} pages{chapter_note} | source {src_size/1e6:.1f} MB -> clean epub {out_size/1e6:.2f} MB"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--catalogue", default="tools/catalogue_seed.json")
    ap.add_argument("--raw-root", default="raw")
    ap.add_argument("--out-root", default="processed")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    catalogue = json.loads((repo_root / args.catalogue).read_text(encoding="utf-8"))
    raw_root = repo_root / args.raw_root
    out_root = repo_root / args.out_root

    if args.all:
        for meta in catalogue:
            process_one(meta, raw_root, out_root)
    elif args.book_id:
        meta = next((m for m in catalogue if m["id"] == args.book_id), None)
        if not meta:
            sys.exit(f"Unknown book id: {args.book_id}")
        process_one(meta, raw_root, out_root)
    else:
        ap.error("provide a book_id or --all")


if __name__ == "__main__":
    main()
