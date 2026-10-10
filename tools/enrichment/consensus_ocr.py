#!/usr/bin/env python3
"""Consensus-correct one OCR copy of a book using an independent OCR copy of the SAME scan.

Pages are matched (the two copies' page indexes drift), words are aligned with difflib, and where the copies disagree on a
single word and exactly one reading is a "valid" word (system dictionary, or a token that occurs >= --min-count times in
BOTH copies, which protects remedy names and abbreviations), that reading is used in the target copy. Disagreements where
neither or both readings are valid are never touched. Every change is logged (page, before, after). The source copy is untouched.

  python3 tools/enrichment/consensus_ocr.py --target <book.json> --other <book.json> --out <book.json> --log <log.json>
"""
import argparse, collections, difflib, json, re
from pathlib import Path

TOK = re.compile(r"\S+")
CORE = re.compile(r"^([^A-Za-z0-9]*)([A-Za-z]+)([^A-Za-z0-9]*)$")      # leading punct / letters / trailing punct

def norm(s): return re.sub(r"\W+", " ", s.lower()).strip()

def main():
    ap = argparse.ArgumentParser()
    for k in ("target", "other", "out", "log"): ap.add_argument("--" + k, required=True)
    ap.add_argument("--min-count", type=int, default=2)
    a = ap.parse_args()
    T = json.loads(Path(a.target).read_text()); O = json.loads(Path(a.other).read_text())
    dic = {w.strip().lower() for w in open("/usr/share/dict/words")}
    cnt = lambda B: collections.Counter(w.lower() for p in B["pages"] for w in re.findall(r"[A-Za-z]+", p["text"]))
    ct, co = cnt(T), cnt(O)
    shared = {w for w in ct if ct[w] >= a.min_count and co.get(w, 0) >= a.min_count}
    valid = lambda w: w.lower() in dic or w.lower() in shared or (w.lower().endswith("s") and w.lower()[:-1] in dic)

    opages = [(p, norm(p["text"])) for p in O["pages"]]
    log, off, changed, unmatched = [], 0, 0, 0
    for tp in T["pages"]:
        nt = norm(tp["text"])
        if len(nt) < 80: continue
        best, bs = None, 0.0
        for d in range(-3, 4):                         # follow the running page offset between the two copies
            j = tp_index = T["pages"].index(tp) + off + d
            if 0 <= j < len(opages):
                s = difflib.SequenceMatcher(None, nt[:700], opages[j][1][:700], autojunk=False).quick_ratio()
                if s > bs: best, bs, bd = opages[j][0], s, d
        if not best or bs < 0.6: unmatched += 1; continue
        off += bd
        tw, ow = tp["text"].split(), best["text"].split()
        tk = [norm(x) for x in tw]; ok = [norm(x) for x in ow]
        sm = difflib.SequenceMatcher(None, tk, ok, autojunk=False)
        out = list(tw)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
                mt, mo = CORE.match(tw[i1]), CORE.match(ow[j1])
                if not (mt and mo): continue
                wt, wo = mt.group(2), mo.group(2)
                if wt == wo or len(wt) < 3 or abs(len(wt) - len(wo)) > 2: continue
                if tw[i1].rstrip(",;:)").endswith("."): continue     # abbreviations (Lyc., Jod., Ars.) are remedy names; never "fix" them toward dictionary words
                # the replacement must be a dictionary word, or a word the target copy itself already uses MORE often than the
                # word it replaces (so a garbled spelling that merely occurs in both copies can never win)
                good = wo.lower() in dic or (wo.lower().endswith("s") and wo.lower()[:-1] in dic) or \
                       (ct.get(wo.lower(), 0) >= 3 and ct.get(wo.lower(), 0) > ct.get(wt.lower(), 0))
                if not valid(wt) and good and difflib.SequenceMatcher(None, wt.lower(), wo.lower()).ratio() >= 0.6:
                    new = mt.group(1) + (wo.capitalize() if wt[0].isupper() and not wt.isupper() else wo.upper() if wt.isupper() and len(wt) > 1 else wo) + mt.group(3)
                    log.append({"page": tp["page_number"], "before": tw[i1], "after": new}); out[i1] = new; changed += 1
        if out != tw: tp["text"] = " ".join(out) if "\n" not in tp["text"] else _rejoin(tp["text"], tw, out)
    T["note"] = (T.get("note") or "") + f" Consensus-corrected against an independent OCR of the same scan: {changed} word corrections (see correction log)."
    Path(a.out).write_text(json.dumps(T, ensure_ascii=False, indent=1))
    Path(a.log).write_text(json.dumps({"changed": changed, "unmatched_pages": unmatched, "log": log}, ensure_ascii=False, indent=1))
    print(f"corrections={changed} unmatched_pages={unmatched}")
    print(collections.Counter((x["before"], x["after"]) for x in log).most_common(30))

def _rejoin(text, old_words, new_words):
    """Replace changed words in-place, preserving the original line breaks."""
    it = iter(zip(old_words, new_words))
    def sub(m):
        o, n = next(it); return n if o == n else n
    return TOK.sub(sub, text)

main()
