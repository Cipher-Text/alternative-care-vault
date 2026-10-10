#!/usr/bin/env python3
"""Parse monographs of the Unani Pharmacopoeia of Bangladesh (Part 1 Vol 4) into structured records."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
BOOK = ROOT / "processed/unani/unani-pharmacopia-of-bangladesh-part1-vol4/book.json"
OUT = Path(__file__).parent / "staging/unani_monographs.json"

def field(p, label_pat, stop_pat):
    m = re.search(label_pat + r"[^:]*:\s*(.*?)(?=" + stop_pat + r"|\Z)", p, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip(" .") if m else None

def clean(v, cut):
    if not v: return v
    v = re.split(cut, v, maxsplit=1)[0]
    v = re.sub(r"\d+\s*\|\s*P\s*a\s*g\s*e", " ", v)
    return re.sub(r"\s+", " ", v).strip(" .,;")

def main():
    d = json.loads(BOOK.read_text())
    t = "\n".join(p["text"] for p in d["pages"])
    parts = re.split(r"\n(?=[A-Z][A-Z'’\- ]{3,}\n\((?:[A-Za-z /]+)\)\n)", t)[1:]
    STOP = r"\n[A-Z][A-Za-z’'‘\- /.]{3,45}(?: \([^)]*\))?\s*:|\n\d+ \| P a g e"
    out = {}
    for p in parts:
        lines = p.split("\n"); name = lines[0].title(); part = lines[1].strip("()")
        key = re.sub(r"[^a-z]", "", name.lower())
        bot = re.search(r"(?:Botanical|Scientific) name\s*[:：]?\s*([A-Z][^\n]{3,80})", p)
        rec = {"name_en": name, "part": part,
               "botanical": clean(bot.group(1), r"\s+(?:Family|b\))") if bot else None,
               "family": field(p, r"b\) Family", r"\n[c-z]\)"),
               "bengali": field(p, r"c\) Bengali name", r"\n[d-z]\)"),
               "english": field(p, r"d\) English name", r"\n\s*\n|Tafseel"),
               "mizaj": clean(field(p, r"Mizaj \(Temperament\)", r"\nMusle|\nBadal|\nMusl"), r"Musle+h?|Bdal|Badal"),
               "actions": field(p, r"Aa.?mal-e-Advia", r"\nMahall|\nMeqdar|\nMuzir"),
               "uses": clean(field(p, r"Mahall-e-Istemalat", r"\nMeqdar|\nMuzir|\nAaham"), r"Meqdar|Muzir|Aaham"),
               "dose": clean(field(p, r"Meqdar-e-khorak", r"\nMuzir|\nAaham"), r"Muzir|Aaham"),
               "side_effects": clean(field(p, r"Muzir", r"\nAaham"), r"Aaham"),
               "habitat": field(p, r"Maskan \(Habitat\)", r"\n[A-Z]"),
               "intro": re.sub(r"\s+", " ", " ".join(lines[2:8]))[:300]}
        if key in out:      # same drug listed under two parts (e.g. Shalgum tuber/seed): keep one, record both parts
            out[key]["part"] += " / " + part
            for k, v in rec.items():
                if not out[key].get(k) and v: out[key][k] = v
        else: out[key] = rec
    OUT.write_text(json.dumps(list(out.values()), ensure_ascii=False, indent=1))
    print(len(out)); 
    for r in out.values(): print(r["name_en"], "|", r["botanical"], "|", r["mizaj"], "|", (r["uses"] or "")[:80], "|", r["dose"])
main()
