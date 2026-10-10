#!/usr/bin/env python3
"""Cross-check + correct a re-OCR'd book against a proofread reference text.

Builds a lexicon from (a) proofread online pages (html in --ref-dir) and (b) /usr/share/dict/words. A token in the OCR
text that is NOT in the lexicon, but is within edit-distance 1 (2 for long words) of exactly one frequent lexicon word,
is corrected. Nothing is changed when the choice is ambiguous. Every change is logged to --log (page, before, after,
reason) so corrections are auditable and reversible. Operates on a book.json copy; the original book is untouched.

  python3 tools/enrichment/correct_ocr_lexicon.py --book processed/.../book.json --ref-dir <html dir> --out <book.json> --log <log.json>
"""
import argparse, collections, html, json, re, sys
from pathlib import Path

TOKEN = re.compile(r"[A-Za-z][A-Za-z'’\-]*[A-Za-z]|[A-Za-z]")

def ref_text(path):
    t = Path(path).read_text(errors="ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", t))

# letter pairs OCR commonly confuses (stored as unordered 2-char sets of the two letters)
CONFUSIONS = {q for p in ["ce", "oc", "un", "hb", "il", "ft", "fj", "ao", "eo", "sz", "mn", "rv", "ij", "ae", "ti", "tl", "nu", "sf", "ln"] for q in (p, p[::-1])}

def variants(w, alphabet="abcdefghijklmnopqrstuvwxyz"):
    s = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    dels = {a + b[1:] for a, b in s if b}
    trans = {a + b[1] + b[0] + b[2:] for a, b in s if len(b) > 1}
    reps = {a + c + b[1:] for a, b in s if b for c in alphabet}
    ins = {a + c + b for a, b in s for c in alphabet}
    return dels | trans | reps | ins

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True); ap.add_argument("--ref-dir", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--log", required=True)
    ap.add_argument("--min-ref-count", type=int, default=3)
    a = ap.parse_args()

    ref = collections.Counter()
    for f in Path(a.ref_dir).glob("*.html"):
        ref.update(w.lower() for w in TOKEN.findall(ref_text(f)))
    sysdict = {w.strip().lower() for w in open("/usr/share/dict/words")}
    book = json.loads(Path(a.book).read_text())
    own = collections.Counter(w.lower() for p in book["pages"] for w in TOKEN.findall(p["text"]))

    known = {w for w, c in ref.items() if c >= 1} | sysdict
    # correction targets: words that are frequent in the proofread text (reliable spellings)
    targets = {w for w, c in ref.items() if c >= a.min_ref_count and len(w) >= 4}
    print(f"ref tokens={sum(ref.values())} vocab={len(ref)} targets={len(targets)} book vocab={len(own)}", file=sys.stderr)

    def stem_known(w):
        return w in known or (w.endswith("s") and w[:-1] in known) or (w.endswith("es") and w[:-2] in known) \
            or (w.endswith("ies") and w[:-3] + "y" in known)
    def same_spelling(x, y):                      # hemorrhoids/haemorrhoids etc. are style variants, not OCR errors
        n = lambda z: z.replace("ae", "e").replace("oe", "e").replace("ou", "o")
        return n(x) == n(y)
    fix, why, suggest = {}, {}, {}
    for w, c in own.items():
        if len(w) < 5 or "-" in w or "'" in w or stem_known(w): continue
        # (1) the 'oe' ligature OCR'd as 'ce' (cedema, diarrhcea, leucorrhcea, cesophagus ...)
        lig = None
        for a_, b_ in (("cea", "oea"), ("ce", "oe")):
            if a_ in w:
                cand = w.replace(a_, b_, 1)
                if ref.get(cand, 0) >= 5: lig = cand; break
        if lig: fix[w], why[w] = lig, "ligature oe->ce"; continue
        # (2) a single-letter OCR confusion in a RARE token, toward a VERY common proofread word.
        if c > 3: continue
        cands = {v for v in variants(w) if v in targets and ref[v] >= 50 and len(v) == len(w)
                 and not v.startswith(w) and not w.startswith(v) and not same_spelling(w, v)
                 and sum(x != y for x, y in zip(w, v)) == 1
                 and not (w[:-1] == v[:-1] and w[-1] in "aeiou" and v[-1] in "aeiou")      # Latin endings (vaginae/vagina)
                 and all((x + y) in CONFUSIONS for x, y in zip(w, v) if x != y)}
        if len(cands) == 1:
            v = next(iter(cands)); fix[w], why[w] = v, "ocr-confusion"
        else:                                                # anything weaker is only suggested, never applied
            weak = {v for v in variants(w) if v in targets and ref[v] >= 10 and not v.startswith(w) and not w.startswith(v)
                    and not same_spelling(w, v)}
            if len(weak) == 1: suggest[w] = next(iter(weak))

    log, changed = [], 0
    def case(src, dst):
        return dst.upper() if src.isupper() and len(src) > 1 else (dst.capitalize() if src[0].isupper() else dst)
    for p in book["pages"]:
        def sub(m):
            w = m.group(0); lw = w.lower()
            nxt = p["text"][m.end():m.end() + 1]
            if lw in fix and nxt != "-":                      # a trailing hyphen means a line-break fragment (urina- tion)
                new = case(w, fix[lw]); log.append({"page": p["page_number"], "before": w, "after": new, "reason": why[lw]}); return new
            return w
        p["text"] = TOKEN.sub(sub, p["text"])
    changed = len(log)
    book["note"] = (book.get("note") or "") + f" Lexicon-corrected against proofread online reference text: {changed} token corrections (see correction log)."
    Path(a.out).write_text(json.dumps(book, ensure_ascii=False, indent=1))
    Path(a.log).write_text(json.dumps({"fixes": fix, "suggestions_not_applied": suggest, "log": log}, ensure_ascii=False, indent=1))
    print(f"unique fixes={len(fix)} token changes={changed}")
    print(sorted(fix.items(), key=lambda kv: -own[kv[0]])[:40])
main()
