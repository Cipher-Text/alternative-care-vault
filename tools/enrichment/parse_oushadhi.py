#!/usr/bin/env python3
"""Parse the Oushadhi Therapeutic Index (formulations with Indication / Dosage) into structured records."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
d = json.loads((ROOT / "processed/ayurveda/oushadhi-therapeutic-index-2019/book.json").read_text())
t = "\n".join(p["text"] for p in d["pages"])
blocks = re.split(r"\n(?=\d+\.\s+[A-Z][A-Z \-\(\)\.,/]+?(?::|\n))", t)
out = {}
def f(b, label, stop):
    m = re.search(label + r"\s*:\s*(.*?)(?=" + stop + r"|\Z)", b, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip(" .") if m else None
for b in blocks:
    m = re.match(r"\d+\.\s+([A-Z][A-Z \-\(\)\.,/]+?)(?::|\n)\s*(\([^)\n]*\))?", b)
    if not m: continue
    name = m.group(1).strip().title()
    rec = {"name_en": name, "reference": (m.group(2) or "").strip("() "),
           "ingredients": f(b, r"(?:Main )?[Ii]ngredients", r"\n(?:Indication|Dosage|Presentation|Total)"),
           "indication": f(b, r"Indications?", r"\n(?:Dosage|Presentation|Anupana)"),
           "dosage": f(b, r"Dosage", r"\n(?:Presentation|Anupana|\d+\.\s)"),
           "presentation": f(b, r"Presentation", r"\n\d+\.\s|\Z")}
    if rec["indication"] and name.lower() not in out: out[name.lower()] = rec
(Path(__file__).parent / "staging/oushadhi_formulations.json").write_text(json.dumps(list(out.values()), ensure_ascii=False, indent=1))
print(len(out), sum(1 for r in out.values() if r["dosage"]))
for r in list(out.values())[:3]: print(json.dumps(r, ensure_ascii=False))
