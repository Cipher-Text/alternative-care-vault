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


# Books whose raw PDF carries its own embedded outline/bookmarks (a real, publisher- or
# author-authored chapter structure, not a regex guess). For these, chapters come straight
# from pypdf's `.outline` instead of `detect_chapters`'s text-pattern matching.
PDF_OUTLINE_CHAPTER_BOOKS = {"oushadhi-therapeutic-index-2019"}


def detect_chapters_from_pdf_outline(reader):
    """Reads a PDF's embedded outline (bookmarks) into the same chapters[] shape as
    detect_chapters. Destination page numbers from pypdf are 0-indexed; +1 to match the
    1-indexed page_number scheme parse_source_pdf() assigns."""
    chapters = []

    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            try:
                start_page = reader.get_destination_page_number(item) + 1
            except Exception:
                continue
            title = (item.title or "").strip()
            m = re.match(r"^Ch-(\d+)\s*-?\s*(.*)$", title, re.IGNORECASE)
            if m:
                chapters.append(
                    {
                        "label": f"Chapter {int(m.group(1))}",
                        "title": m.group(2).strip(" -"),
                        "start_page": start_page,
                    }
                )
            else:
                chapters.append({"label": title, "start_page": start_page})

    if reader.outline:
        walk(reader.outline)
    return chapters


# Books whose raw EPUB's nav.xhtml still carries a real, publisher-authored chapter TOC
# (with direct per-chapter page anchors) even though the generic page-text parser never
# reads nav.xhtml. Currently just micozzi: its one-off PDF-to-EPUB conversion script (long
# gone, see REQUIRES_DEDICATED_SCRIPT-adjacent note in catalogue_seed.json) preserved the
# original textbook's full TOC in nav.xhtml as a side effect of mimicking IA's EPUB layout.
EPUB_NAV_CHAPTER_BOOKS = {"micozzi-fundamentals-of-complementary-and-alternative-medicine-5th"}


def detect_chapters_from_epub_nav(epub_path):
    """Reads chapter-level <a> entries (text starting "Chapter N ...") out of a raw EPUB's
    nav.xhtml, using each entry's #page-N fragment as start_page. Front-matter/section/
    sub-heading TOC entries (no "Chapter N" prefix) are skipped, not just chapters missing
    a page anchor."""
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
        nav_item = next(
            (
                item
                for item in opf.findall(f".//{{{NS_OPF}}}manifest/{{{NS_OPF}}}item")
                if item.get("properties") == "nav"
            ),
            None,
        )
        if nav_item is None:
            return []

        nav_path = opf_dir / nav_item.get("href")
        if not nav_path.exists():
            return []
        html = nav_path.read_text(encoding="utf-8")
        try:
            root = ET.fromstring(html.encode("utf-8"))
        except ET.ParseError:
            return []

        chapters = []
        for a in root.iter(f"{{{NS_XHTML}}}a"):
            text = "".join(a.itertext()).strip()
            m = re.match(r"^Chapter\s+(\d+)\s+(.+)$", text)
            if not m:
                continue
            page_m = re.search(r"#page-(\d+)", a.get("href", ""))
            if not page_m:
                continue
            chapters.append(
                {
                    "label": f"Chapter {m.group(1)}",
                    "title": m.group(2).strip(),
                    "start_page": int(page_m.group(1)),
                }
            )
        return chapters


# Books needing chapter-number normalization beyond what CHAPTER_PATTERNS's stateless
# per-match regex can do -- currently just madhava-nidana-vol-1-lochan (see
# detect_chapters_madhava_nidana's docstring).
STATEFUL_CHAPTER_BOOKS = {"madhava-nidana-vol-1-lochan"}

# OCR digit-confusables seen in madhava-nidana-vol-1-lochan's chapter-number labels: 'I',
# ']', '!' and 'l' are all misread for the digit '1' (e.g. "2I" for 21, "3]" for 31, and
# critically the leading '1' of a two-digit number is sometimes dropped entirely rather
# than misread -- see detect_chapters_madhava_nidana).
_MADHAVA_NIDANA_DIGIT_FIX = str.maketrans({"I": "1", "]": "1", "!": "1", "l": "1"})

_MADHAVA_NIDANA_HEADING_RE = re.compile(
    r"\bCHAPTER\s+(\S+)\s*['’]?\s*"  # chapter number, optional stray OCR quote
    r"([ऀ-ॿ][ऀ-ॿ‌\-]*)\s+"  # Devanagari chapter-title word
    r"([^ऀ-ॿ]{2,150}?)"  # transliteration/English gloss, up to...
    r"(?=[ऀ-ॿ])"  # ...the next Devanagari run (the opening Sanskrit verse)
)


def detect_chapters_madhava_nidana(pages):
    """madhava-nidana-vol-1-lochan-specific. Real chapter headings are ALL-CAPS "CHAPTER N"
    immediately followed by the Devanagari chapter title, its transliteration, and usually
    a parenthetical English gloss, e.g. "CHAPTER 9 दाहनिदानम्‌ Daha Nidanam (...BURNING...)".
    This shape reliably distinguishes real headings from two false-positive sources found in
    this book's OCR text: the front-matter table of contents (plain "CHAPTER N Title ###
    Title2 ###...", no adjacent Devanagari, so it never matches) and mixed-case inline
    citations to other chapters/texts within running prose ("Chapter 24 of ... Text" --
    excluded by requiring the literal, all-caps "CHAPTER").

    The chapter *number* needs repair, not just the heading match: OCR frequently drops the
    leading "1" of two-digit numbers outright (13 -> "3", 17 -> "7", 18 -> "8", 19 -> "9")
    while other numbers come through with digit-like noise instead (I/]/! for "1", e.g. "2I"
    for 21, "3]" for 31). Verified against this book's own front-matter TOC titles for every
    number below 33 -- beyond chapter ~32 the OCR text stops saying "CHAPTER" at all (no
    heading of any kind, checked across the rest of the book), so coverage stops there; only
    chapters 9 and 11 are missing within that range, apparently for the same reason. Treat
    this as best-effort, same as the other CHAPTER_PATTERNS books."""
    chapters = []
    prev_num = 0
    for p in pages:
        for m in _MADHAVA_NIDANA_HEADING_RE.finditer(p["text"]):
            digits = re.sub(r"\D", "", m.group(1).translate(_MADHAVA_NIDANA_DIGIT_FIX))
            if not digits:
                continue
            num = int(digits)
            if num <= prev_num:
                retried = int("1" + digits)
                if retried > prev_num:
                    num = retried
            prev_num = num
            title = re.sub(r"\s+", " ", m.group(3)).strip(" .,-")
            if ")" in title:
                title = title[: title.index(")") + 1]
            chapters.append({"label": f"Chapter {num}", "title": title, "start_page": p["page_number"]})
    return chapters


# adams-practical-guide-to-homeopathic-treatment-1913: needs both a PART and a CHAPTER
# marker (Part-level numbering restarts each Part's Chapter numbering at "I"), so this
# doesn't fit CHAPTER_PATTERNS's single-pattern/single-label shape either.
ADAMS_CHAPTER_BOOKS = {"adams-practical-guide-to-homeopathic-treatment-1913"}

_ADAMS_HEADING_RE = re.compile(
    r"\b(PART|CHAPTER)\s+([IVXLC0-9]+)\.?\s+"
    r"([A-Z0-9 ,.'\-?!:&]*?)(?=[a-z]|\bPART\b|\bCHAPTER\b|$)"
)


def detect_chapters_adams(pages):
    """adams-practical-guide-to-homeopathic-treatment-1913-specific. Real PART/CHAPTER
    headings are ALL-CAPS ("PART II. DISEASES AND THEIR TREATMENT."); a lowercase "Chapter"
    elsewhere is always an inline cross-reference in running prose ("Chapter I., as it is
    fundamental...") and is excluded just by requiring literal uppercase. That alone isn't
    enough, though: the front-matter table of contents (pages 1-20) is *also* ALL-CAPS
    "PART/CHAPTER N. Title" and matches the same shape, so pages before 21 (where the real
    text begins) are skipped explicitly.
    The book has 3 Parts; Part I and II each open directly into their own "Chapter I" with no
    separate Part-level title text (so those Part matches capture an empty title and are
    dropped, matching real book structure), while Part III (the Materia Medica) has a real
    title of its own and no further "CHAPTER" subdivision at all -- verified by scanning the
    entire book for any other occurrence of literal "CHAPTER", case-sensitive: there are none
    beyond Part I's four chapters and Part II's first (and only) chapter. Chapter numbering
    restarts at "I" per Part, so labels are qualified with their Part."""
    chapters = []
    current_part = None
    for p in pages:
        if p["page_number"] is not None and p["page_number"] < 21:
            continue  # front-matter table of contents
        for m in _ADAMS_HEADING_RE.finditer(p["text"]):
            kind, num = m.group(1), m.group(2)
            if num == "11":  # OCR misread of the roman numeral "II"
                num = "II"
            title_chars = m.group(3)
            term_idxs = [title_chars.index(c) for c in ".?!" if c in title_chars]
            if term_idxs:
                title_chars = title_chars[: min(term_idxs)]
            title = title_chars.strip(" .,-")
            if kind == "PART":
                current_part = num
                if title:
                    chapters.append({"label": f"Part {num}", "title": title, "start_page": p["page_number"]})
            else:
                label = f"Part {current_part}, Chapter {num}" if current_part else f"Chapter {num}"
                chapters.append({"label": label, "title": title, "start_page": p["page_number"]})
    return chapters


# bhavaprakasha-vol-1-srikantha-murthy-2001: chapter 6 alone has 24 numbered sub-chapters
# (varga groups), so this needs roman-numeral bookkeeping CHAPTER_PATTERNS can't do either.
BHAVAPRAKASHA_CHAPTER_BOOKS = {"bhavaprakasha-vol-1-srikantha-murthy-2001"}

_BHAVAPRAKASHA_HEADING_RE = re.compile(r"\bChapter\s*-?\s*(\d+)\s*\(?([IVXLC]*)\)?\s*(.{2,140})")
_BHAVAPRAKASHA_NAME_RE = re.compile(
    r"([A-Za-z][A-Za-z .]{0,40}?(?:[Pp]rakaran(?:a|am)|[Vv]arga))\s*[—\-\(]\s*([A-Za-z][^)\n]{2,70})\)?"
)
_ROMAN_STRICT_RE = re.compile(r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s):
    if not s or not _ROMAN_STRICT_RE.match(s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN_VALUES[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def _int_to_roman(n):
    values = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
              (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, sym in values:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def detect_chapters_bhavaprakasha(pages):
    """bhavaprakasha-vol-1-srikantha-murthy-2001-specific. Real chapter/sub-chapter openings
    look like "Chapter-6 (XVI) ... Takra Varga (Group of Butter milks) ..." -- a main chapter
    number, an optional roman-numeral sub-chapter marker in parens (only chapters 6 and 7
    have sub-chapters -- 24 "varga" groups and 7 "prakarana" procedures respectively), then a
    garbled-OCR transliteration leading into the real "<Name> Prakarana/Varga (<English
    gloss>)" title. Two false-positive sources are excluded: footnote citations in the
    verse-numbering style "Bh. pr. Chapter 2/1" (title text starting with "/"), and appendix
    cross-references like "(Ref. Chapter- 6 ...)" (excluded by checking the 40 chars before
    the match for "Ref").

    The sub-chapter roman numeral is trusted when it parses as strict, well-formed roman
    numerals (validated, not just character-class matched -- OCR garbles some, e.g. "TIT"
    for "(III)" or "VIL" for "(VIII)", which fail strict validation on purpose) and only
    synthesized as (previous sub-number for this chapter) + 1 when missing/unparseable.
    Do NOT switch this to a running positional counter instead of trusting valid OCR values
    -- chapter 6's sub-chapter XV (Dadhi Varga) has no extractable heading at all, and a pure
    counter silently shifts every subsequent sub-chapter's label off by one as a result,
    mislabeling e.g. the real "(XVI) Takra Varga" as "(XV)". Trusting valid OCR digits and
    only bridging actual gaps avoids that. Verified against this book's own front-matter
    chapter list. Best-effort, same as the other CHAPTER_PATTERNS books -- titles especially
    may retain OCR noise (this book's OCR is comparatively heavily garbled)."""
    raw = []
    for p in pages:
        text = p["text"]
        for m in _BHAVAPRAKASHA_HEADING_RE.finditer(text):
            if "Ref" in text[max(0, m.start() - 40): m.start()]:
                continue
            chunk = m.group(3)
            if chunk.lstrip().startswith("/"):
                continue
            raw.append({"num": int(m.group(1)), "roman": m.group(2), "page": p["page_number"], "chunk": chunk})

    counts = {}
    for r in raw:
        counts[r["num"]] = counts.get(r["num"], 0) + 1

    chapters = []
    last_sub = {}
    for r in raw:
        n = r["num"]
        val = _roman_to_int(r["roman"])
        if val is None:
            val = last_sub.get(n, 0) + 1
        last_sub[n] = val

        m2 = _BHAVAPRAKASHA_NAME_RE.search(r["chunk"])
        if m2:
            title = f"{m2.group(1).strip()} ({m2.group(2).strip()})"
        else:
            title = re.sub(r"\s+", " ", r["chunk"][:60]).strip()

        label = f"Chapter {n} ({_int_to_roman(val)})" if counts[n] > 1 else f"Chapter {n}"
        chapters.append({"label": label, "title": title, "start_page": r["page"]})
    return chapters


# majumdar-homoeopathic-chikitsa-prakaran-bengali: real headings are Bengali ordinal WORDS
# (not numerals), e.g. "দ্বিতীয় অধ্যায়" (Chapter 2) -- found during a broader sweep of every
# homeopathy book without chapters (not just CHAPTER_PATTERNS's original two), 2026-09-25.
MAJUMDAR_CHAPTER_BOOKS = {"majumdar-homoeopathic-chikitsa-prakaran-bengali"}

# Chapters 1-24 by their expected canonical spelling, plus the specific OCR misreadings
# actually observed in this book (e.g. "ষষ্ঠ"/6th losing its leading letter to "ষ্ঠ",
# "ত্রয়োদশ"/13th misread as "প্রয়োদশ") -- verified against this book's own sequential
# medical topic order (eye, ear, nose, heart, ... skin), not guessed.
_MAJUMDAR_ORDINALS = {
    "প্রথম": 1, "দ্বিতীয়": 2, "তৃতীয়": 3, "চতুর্থ": 4, "পঞ্চম": 5,
    "ষষ্ঠ": 6, "ষ্ঠ": 6,
    "সপ্তম": 7, "অষ্টম": 8, "অক্টম": 8,
    "নবম": 9, "দশম": 10,
    "একাদশ": 11, "দ্বাদশ": 12,
    "ত্রয়োদশ": 13, "প্রয়োদশ": 13,
    "চতুর্দশ": 14, "পঞ্চদশ": 15,
    "ষোড়শ": 16, "যৌড়শ": 16,
    "সপ্তদশ": 17,
    "অষ্টাদশ": 18, "অফ্টাদশ": 18,
    "ঊনবিংশ": 19, "উনবিংশ": 19,
    "বিংশ": 20,
    "একবিংশ": 21, "দ্বাবিংশ": 22, "ত্রয়োবিংশ": 23, "চতুর্বিংশ": 24,
}
_MAJUMDAR_ORDINAL_ALT = "|".join(sorted(_MAJUMDAR_ORDINALS, key=len, reverse=True))
_MAJUMDAR_HEADING_RE = re.compile(
    rf"({_MAJUMDAR_ORDINAL_ALT})\s*(?:অধ্যায়|অন্যায়)[।\s0-9]*([^।]{{2,60}})"
)


def detect_chapters_majumdar(pages):
    """majumdar-homoeopathic-chikitsa-prakaran-bengali-specific. Real chapter headings are
    an ordinal word (see _MAJUMDAR_ORDINALS) immediately followed by "অধ্যায়" ("chapter") --
    or its single observed OCR misreading "অন্যায়" ("wrong/injustice", chapter 1 only) --
    e.g. "দ্বিতীয় অধ্যায়। কর্ণিয়ার পীড়া।" (Chapter 2. Corneal disease.). Numbers come from
    the ordinal word's lookup value directly, not position, so a missing chapter (19, no
    extractable heading anywhere in this OCR text) doesn't shift any later chapter's number
    -- unlike a positional counter would. No front-matter TOC contamination was found for
    this book (each of the 23 recovered chapter numbers appears exactly once), unlike
    Madhava Nidana/Bhavaprakasha, so no page-range exclusion is needed here. Best-effort:
    titles are truncated at the next Bengali danda ("।") and may still carry trailing OCR
    noise when no danda appears within the capture window."""
    chapters = []
    for p in pages:
        for m in _MAJUMDAR_HEADING_RE.finditer(p["text"]):
            num = _MAJUMDAR_ORDINALS[m.group(1)]
            title = re.sub(r"\s+", " ", m.group(2)).strip(" .,-।")
            chapters.append({"label": f"Chapter {num}", "title": title, "start_page": p["page_number"]})
    return chapters


# ernst-oxford-handbook-of-complementary-medicine: real "CHAPTER N Title" headers repeat as
# a running page header on every page within the chapter, not just the opening page, so this
# needs first-occurrence-per-number dedup rather than "every regex match is a new chapter"
# like every other book above.
ERNST_CHAPTER_BOOKS = {"ernst-oxford-handbook-of-complementary-medicine"}

_ERNST_HEADING_RE = re.compile(r"\bCHAPTER\s+(\d+)\s+([^\n]+)")


def detect_chapters_ernst(pages):
    """ernst-oxford-handbook-of-complementary-medicine-specific. "CHAPTER N <Title>" is
    printed as a running header on every page of that chapter (e.g. "CHAPTER 3 Complementary
    therapies" appears 35 times across chapter 3's own pages), not just once at the chapter's
    actual opening -- confirmed by checking each chapter number's occurrence count and page
    range. So the fix here isn't a false-positive filter like every other book's mechanism
    above; every match IS a real, correctly-labeled chapter occurrence, there are just far
    more of them than there are chapters. Keep only the first (lowest page number) occurrence
    per chapter number. All 7 of this book's chapters recovered, not best-effort -- verified
    monotonically increasing and with no gaps."""
    chapters = []
    seen = set()
    for p in pages:
        for m in _ERNST_HEADING_RE.finditer(p["text"]):
            num = int(m.group(1))
            if num in seen:
                continue
            seen.add(num)
            title = re.sub(r"\s+", " ", m.group(2)).strip()
            chapters.append({"label": f"Chapter {num}", "title": title, "start_page": p["page_number"]})
    return chapters


# latif-yunani-hakimi-chikitsha-pranali-1892: same Bengali-ordinal-word "<ordinal> অধ্যায়"
# convention as majumdar-homoeopathic-chikitsa-prakaran-bengali, found during a sweep of the
# ayurveda/unani chapter-less books, 2026-09-25.
LATIF_CHAPTER_BOOKS = {"latif-yunani-hakimi-chikitsha-pranali-1892"}

# Chapters 1-10 by canonical spelling, plus the specific OCR misreadings observed in this
# book: "ধ্িতীয়" for দ্বিতীয়/2nd (dropped consonant cluster), "অপ্তম" for সপ্তম/7th.
_LATIF_ORDINALS = {
    "প্রথম": 1, "দ্বিতীয়": 2, "ধ্িতীয়": 2, "তৃতীয়": 3, "চতুর্থ": 4, "পঞ্চম": 5,
    "ষষ্ঠ": 6, "সপ্তম": 7, "অপ্তম": 7, "অষ্টম": 8,
    "নবম": 9, "দশম": 10,
}
_LATIF_ORDINAL_ALT = "|".join(sorted(_LATIF_ORDINALS, key=len, reverse=True))
_LATIF_HEADING_RE = re.compile(rf"({_LATIF_ORDINAL_ALT})\s*অধ্যায়(?!ে)[।\s0-9]*([^।]{{2,60}})")


def detect_chapters_latif(pages):
    """latif-yunani-hakimi-chikitsha-pranali-1892-specific. Real headings are an ordinal word
    immediately followed by bare "অধ্যায়" ("chapter") + danda, e.g. "তৃতীয় অধ্যায়। ফাস্ত বা
    রক্তমোক্ষণ প্রক্রিয়া।" (Chapter 3. Bloodletting procedure.) -- same convention as
    majumdar-homoeopathic-chikitsa-prakaran-bengali. Two false-positive sources excluded:
    inline cross-references use the locative form "অধ্যায়ে" ("in the chapter") instead of
    bare "অধ্যায়" -- excluded via a negative lookahead for the trailing "ে", not just a
    different regex -- and page 7 is a standalone errata page ("ভ্রম সংশোধন") that happens to
    mention "অষ্টম অধ্যায়" (chapter 8) as a correction reference, excluded by page number
    since it's the only one. 8 of 10 chapters recovered (1st and 8th have no extractable
    heading anywhere in the OCR text) -- best-effort, same as the other CHAPTER_PATTERNS
    books."""
    chapters = []
    for p in pages:
        if p["page_number"] == 7:
            continue
        for m in _LATIF_HEADING_RE.finditer(p["text"]):
            num = _LATIF_ORDINALS[m.group(1)]
            title = re.sub(r"\s+", " ", m.group(2)).strip(" .,-।")
            chapters.append({"label": f"Chapter {num}", "title": title, "start_page": p["page_number"]})
    return chapters


# sarkar-grihasther-mushtiyog-o-kobirajer-chikitsa-1897: only 3 chapters (পরিচ্ছেদ) exist in
# this book, but "চতুর্থ"/etc doesn't apply -- OCR renders this book's ordinal words FAR less
# consistently than majumdar/latif's "অধ্যায়" convention (its 3rd chapter's ordinal word
# alone was seen spelled ~20 different corrupted ways), so a lookup table isn't practical.
SARKAR_CHAPTER_BOOKS = {"sarkar-grihasther-mushtiyog-o-kobirajer-chikitsa-1897"}

# Only chapters 1 and 2's ordinal word ("প্রথম"/"দ্বিতীয়") comes through recognizably, and
# even then in several corrupted spellings -- these are the ones actually observed.
_SARKAR_KNOWN_ORDINALS = {
    "প্রথম": 1, "প্রথষ": 1, "গ্রথম": 1,
    "দ্বিতীয়": 2, "দ্বিতীঘ্ন": 2, "দদ্বতীয়": 2,
}
_SARKAR_HEADING_RE = re.compile(
    r"(\S{1,15})\s*পরিচ্ছেদ(?!ে)[।\s0-9০-৯]*([^।]{2,50}(?:।\s*[^।]{2,50})?)"
)


def detect_chapters_sarkar(pages):
    """sarkar-grihasther-mushtiyog-o-kobirajer-chikitsa-1897-specific. Like Ernst, real
    "<ordinal> পরিচ্ছেদ" ("chapter") headings repeat as a running header on every page of a
    chapter, not just its opening page, so this keeps only the first occurrence -- but unlike
    Ernst, the chapter number itself needs a lookup (Bengali ordinal words), and unlike
    majumdar/latif's ordinal words, OCR mangles this book's 3rd-chapter ordinal ("তৃতীয়")
    into so many different unrecognizable spellings that no lookup table is practical. Since
    this book has verifiably only 3 chapters (confirmed by reading to the book's own final
    page, which is a publisher's ad for the not-yet-released Volume 2), any occurrence that
    isn't chapter 1 or 2's word is inferred to be chapter 3 -- but only once both 1 and 2 have
    already been found, so an early unrelated match can't be mistaken for it. Inline
    cross-references use the locative "পরিচ্ছেদে" ("in the chapter") instead of bare
    "পরিচ্ছেদ" -- excluded via a negative lookahead, same trick as latif. The front-matter
    table of contents (pages before 59, where the real chapter 1 heading is) also matches the
    same bare-word shape and needs its own exclusion, unlike latif where it didn't.
    Titles are messy best-effort here: the two-danda capture window pulls in a sub-section
    label ("১ম প্রকরণ") plus, when present, its topic name, but page 97 (chapter 2's start)
    happens to be a transitional page where the chapter boundary falls mid-paragraph, so its
    title is leftover text from the prior topic rather than chapter 2's real subject."""
    chapters = {}
    for p in pages:
        if p["page_number"] is not None and p["page_number"] < 59:
            continue
        for m in _SARKAR_HEADING_RE.finditer(p["text"]):
            num = _SARKAR_KNOWN_ORDINALS.get(m.group(1))
            if num is None:
                if 1 in chapters and 2 in chapters and 3 not in chapters:
                    num = 3
                else:
                    continue
            if num in chapters:
                continue
            title = re.sub(r"\s+", " ", m.group(2)).strip(" .,-।")
            chapters[num] = {"label": f"Chapter {num}", "title": title, "start_page": p["page_number"]}
    return [chapters[n] for n in sorted(chapters)]


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


# Books processed by a dedicated one-off script (not in this repo) whose source EPUB
# doesn't match the generic parser's assumptions (e.g. body text in <div>s instead of
# <p>s). The generic parser doesn't cleanly fail on them -- it silently extracts a
# handful of garbage "pages" from incidental <p> tags (marketing boilerplate, duplicate
# TOC fragments) -- so routing them through --all would silently overwrite a correct,
# carefully-extracted processed/ output with garbage. Regenerating these requires
# rebuilding their one-off extraction script first.
REQUIRES_DEDICATED_SCRIPT = {"heinrich-fundamentals-of-pharmacognosy-and-phytotherapy-4th"}


def process_one(meta, raw_root, out_root):
    raw_path = raw_root / meta["raw_file"]
    if not raw_path.exists():
        print(f"SKIP (missing source): {raw_path}")
        return
    if meta["id"] in REQUIRES_DEDICATED_SCRIPT:
        print(f"SKIP {meta['id']}: requires its dedicated one-off extraction script, "
              f"not the generic parser (see REQUIRES_DEDICATED_SCRIPT docstring above)")
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

    if meta["id"] in PDF_OUTLINE_CHAPTER_BOOKS:
        chapters = detect_chapters_from_pdf_outline(pypdf.PdfReader(raw_path))
    elif meta["id"] in EPUB_NAV_CHAPTER_BOOKS:
        chapters = detect_chapters_from_epub_nav(raw_path)
    elif meta["id"] in STATEFUL_CHAPTER_BOOKS:
        chapters = detect_chapters_madhava_nidana(pages)
    elif meta["id"] in ADAMS_CHAPTER_BOOKS:
        chapters = detect_chapters_adams(pages)
    elif meta["id"] in BHAVAPRAKASHA_CHAPTER_BOOKS:
        chapters = detect_chapters_bhavaprakasha(pages)
    elif meta["id"] in MAJUMDAR_CHAPTER_BOOKS:
        chapters = detect_chapters_majumdar(pages)
    elif meta["id"] in ERNST_CHAPTER_BOOKS:
        chapters = detect_chapters_ernst(pages)
    elif meta["id"] in LATIF_CHAPTER_BOOKS:
        chapters = detect_chapters_latif(pages)
    elif meta["id"] in SARKAR_CHAPTER_BOOKS:
        chapters = detect_chapters_sarkar(pages)
    else:
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
