#!/usr/bin/env python3
"""
Build a queryable SQLite database (with full-text search) from processed/catalogue.json
and the per-book processed/<discipline>/<id>/book.json files.

Usage:
    python3 tools/build_library_db.py [--out db/library.db] [--processed-root processed]
"""
import argparse
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    editor TEXT,
    translator TEXT,
    year INTEGER,
    edition TEXT,
    volume TEXT,
    language TEXT,
    discipline TEXT NOT NULL,
    page_count INTEGER,
    source_raw_file TEXT,
    processed_epub TEXT,
    processed_json TEXT
);

CREATE TABLE pages (
    id INTEGER PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id),
    page_index INTEGER NOT NULL,
    page_number INTEGER,
    label TEXT,
    text TEXT NOT NULL
);
CREATE INDEX idx_pages_book ON pages(book_id);

CREATE TABLE chapters (
    id INTEGER PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id),
    chapter_index INTEGER NOT NULL,
    label TEXT NOT NULL,
    title TEXT,
    start_page INTEGER
);
CREATE INDEX idx_chapters_book ON chapters(book_id);

CREATE VIRTUAL TABLE pages_fts USING fts5(
    text, content='pages', content_rowid='id'
);
"""


def build(processed_root, out_path):
    catalogue = json.loads((processed_root / "catalogue.json").read_text(encoding="utf-8"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    con = sqlite3.connect(out_path)
    con.executescript(SCHEMA)

    for entry in catalogue:
        con.execute(
            """INSERT INTO books
               (id, title, author, editor, translator, year, edition, volume,
                language, discipline, page_count, source_raw_file, processed_epub, processed_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"], entry["title"], entry.get("author"), entry.get("editor"),
                entry.get("translator"), entry.get("year"), entry.get("edition"),
                entry.get("volume"), entry.get("language"), entry["discipline"],
                entry.get("page_count"), entry.get("source_raw_file"),
                entry.get("processed_epub"), entry.get("processed_json"),
            ),
        )

        book_json = processed_root.parent / entry["processed_json"]
        book = json.loads(book_json.read_text(encoding="utf-8"))
        for i, page in enumerate(book["pages"], start=1):
            con.execute(
                "INSERT INTO pages (book_id, page_index, page_number, label, text) VALUES (?, ?, ?, ?, ?)",
                (entry["id"], i, page.get("page_number"), page.get("label"), page["text"]),
            )
        for i, chapter in enumerate(book.get("chapters", []), start=1):
            con.execute(
                "INSERT INTO chapters (book_id, chapter_index, label, title, start_page) VALUES (?, ?, ?, ?, ?)",
                (entry["id"], i, chapter["label"], chapter.get("title"), chapter.get("start_page")),
            )

    con.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
    con.commit()

    n_books = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    n_pages = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    n_chapters = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    con.close()
    print(
        f"Built {out_path} — {n_books} books, {n_pages} pages indexed for full-text search, "
        f"{n_chapters} chapters."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="db/library.db")
    ap.add_argument("--processed-root", default="processed")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    build(repo_root / args.processed_root, repo_root / args.out)


if __name__ == "__main__":
    main()
