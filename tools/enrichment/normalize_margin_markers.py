#!/usr/bin/env python3
"""Turn OCR'd margin markers into explicit bar marks.

Some books grade each line with a margin glyph (Hering's *Guiding Symptoms*: a thick bar, or a double bar). Tesseract reads these as
letters/digits glued to the first word of the line (`tPulse`, `IFace`, `1Nausea`, `11Tenesmus`, `!1Urine`, `HViolent`), which makes
real words look garbled. At the START OF A LINE only, a 1-3 character prefix drawn from the confusable set is replaced by `|` (one
glyph) or `||` (two or more) plus a space, so the grade survives and the word is clean again.

  python3 tools/enrichment/normalize_margin_markers.py --book <book.json> --out <book.json> --log <log.json> [--glyphs "Il1t!iH|"]
Note: because `|` is itself in the junk-character set used by the quality metrics, measure such books with `|` excluded."""
import argparse, collections, json, re
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    for k in ("book", "out", "log"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--glyphs", default="Il1t!iH|")
    ap.add_argument("--midline", action="store_true",
                    help="also strip a ONE-character glyph prefix glued to a lowercase word anywhere in a line (inline sub-items), same validity rule")
    a = ap.parse_args()
    B = json.loads(Path(a.book).read_text())
    cls = "[" + re.escape(a.glyphs) + "]"
    pat = re.compile(rf"(?m)^([ \t]*)({cls}{{1,3}})(?=[A-Z][a-z]{{2,}})")
    # lowercase pass: marker glued before a lowercase word ("bsudden", "tneck", "fpain"). Only at a line start, only when the whole
    # token is not a valid word and the remainder is (dictionary word, or >= 3 occurrences elsewhere in this book).
    dic = {w.strip().lower() for w in open("/usr/share/dict/words")}
    cnt = collections.Counter(w.lower() for pg in B["pages"] for w in re.findall(r"[A-Za-z]+", pg["text"]))
    ok = lambda w: w in dic or (w.endswith("s") and w[:-1] in dic) or cnt.get(w, 0) >= 3
    low = re.compile(r"(?m)^([ \t]*)([A-Za-z!|]{1,2})([a-z]{3,})(?![A-Za-z])")
    log, n = collections.Counter(), 0
    for p in B["pages"]:
        def sub(m):
            nonlocal n
            g = m.group(2); n += 1; log[g] += 1
            return m.group(1) + ("| " if len(g) == 1 else "|| ")
        p["text"] = pat.sub(sub, p["text"])
        def sub_low(m):
            nonlocal n
            pre, rest = m.group(2), m.group(3)
            if ok((pre + rest).lower()) or not ok(rest.lower()): return m.group(0)
            n += 1; log["lc:" + pre] += 1
            return m.group(1) + ("| " if len(pre) == 1 else "|| ") + rest
        p["text"] = low.sub(sub_low, p["text"])
        if a.midline:
            def sub_mid(m):
                nonlocal n
                pre, rest = m.group(1), m.group(2)
                if ok((pre + rest).lower()) or not ok(rest.lower()): return m.group(0)
                n += 1; log["mid:" + pre] += 1
                return "| " + rest
            p["text"] = re.sub(r"(?<![A-Za-z0-9])([ilItfuwbkenH!|1])([a-z]{4,})(?![A-Za-z])", sub_mid, p["text"])
    B["note"] = (B.get("note") or "") + f" Margin markers normalised to | / || ({n} line starts; see log)."
    Path(a.out).write_text(json.dumps(B, ensure_ascii=False, indent=1))
    Path(a.log).write_text(json.dumps({"changed": n, "by_glyph": log.most_common()}, ensure_ascii=False, indent=1))
    print(f"normalised {n} line-start markers;", log.most_common(10))
main()
