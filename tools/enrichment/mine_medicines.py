#!/usr/bin/env python3
"""Mine remedy candidates from the processed homeopathy books.

Headings come from Boericke's Pocket Manual ("ALOE. (Socotrine Aloes.)"). OCR noise is filtered by
requiring each candidate name to be corroborated by other books. Duplicates of existing records
(incl. aliases / abbreviations / spelling variants) are dropped. Output: staging/candidate_medicines.json
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, HERE, Registry, load_existing, norm

BOERICKE = "boericke-pocket-manual-of-homoeopathic-materia-medica-3rd"
HEADING = re.compile(r'(?<![A-Za-z])([A-Z][A-Z\-]{2,}(?: [A-Z][A-Z\-]{2,}){0,3})\.\s*\(([^)]{3,80})\)')
MIN_BOOKS = 4
# Core polychrests Boericke prints without a "(common name)" parenthetical, so HEADING misses them.
MUST_HAVE = ["Sulphur", "Lachesis", "Bryonia Alba", "Ipecacuanha", "Natrum Muriaticum", "Sepia", "Hepar Sulphuris",
             "Calendula", "Hypericum", "Hamamelis", "Cantharis", "Chamomilla", "Carbo Vegetabilis", "Causticum",
             "Kali Bichromicum", "Lachesis Muta", "Magnesia Phosphorica", "Natrum Sulphuricum", "Rumex Crispus"]

def book_texts():
    out = {}
    for p in sorted((ROOT / "processed/homeopathy").glob("*/book.json")):
        d = json.loads(p.read_text())
        if d.get("language", "en").lower().startswith(("bn", "beng")): continue
        out[d["id"]] = norm(" ".join(pg["text"] for pg in d["pages"]))
    return out

def main():
    reg = Registry("medicines", load_existing("medicines"))
    texts = book_texts()
    pages = json.loads((ROOT / f"processed/homeopathy/{BOERICKE}/book.json").read_text())["pages"]
    full = " ".join(p["text"] for p in pages)
    heads = [(m.start(), m.end(), m.group(1).title(), m.group(2).strip(" .,")) for m in HEADING.finditer(full)]
    cands, seen, skipped = [], {}, {"duplicate_existing": [], "duplicate_in_batch": [], "uncorroborated": []}
    for i, (s, e, name, common) in enumerate(heads):
        canon, how = reg.lookup(name)
        if canon and reg.is_existing(canon):
            skipped["duplicate_existing"].append({"heading": name, "matches": canon, "via": how}); continue
        k = norm(name)
        if k in seen or any(k == x or k.startswith(x + " ") or x.startswith(k + " ") and len(k.split()) == 1 for x in seen):
            skipped["duplicate_in_batch"].append(name); continue
        nbooks = sum(1 for t in texts.values() if re.search(r'\b' + re.escape(k) + r'\b', t))
        if nbooks < MIN_BOOKS:
            skipped["uncorroborated"].append({"heading": name, "books": nbooks}); continue
        body = full[e: heads[i + 1][0] if i + 1 < len(heads) else e + 6000][:6000]
        dose = re.search(r'Dose\.?\s*[—-]?\s*(.{0,160}?)(?:\.|$)', body)
        seen[k] = name
        cands.append({"name_en": name, "common_name": common, "books_mentioning": nbooks,
                      "boericke_dose": dose.group(1).strip() if dose else None,
                      "boericke_excerpt": re.sub(r"\s+", " ", body[:900]).strip(), "source": f"{BOERICKE}"})
    for name in MUST_HAVE:
        canon, _ = reg.lookup(name)
        k = norm(name)
        if (canon and reg.is_existing(canon)) or k in seen: continue
        m = re.search(r'(?<![A-Za-z])' + re.escape(name.upper()) + r'\.\s', full)
        if not m: skipped["uncorroborated"].append({"heading": name, "books": "no-heading"}); continue
        body = full[m.end(): m.end() + 6000]
        dose = re.search(r'Dose\.?\s*[—-]?\s*(.{0,160}?)(?:\.|$)', body)
        nbooks = sum(1 for t in texts.values() if re.search(r'\b' + re.escape(k) + r'\b', t))
        seen[k] = name
        cands.append({"name_en": name, "common_name": None, "books_mentioning": nbooks,
                      "boericke_dose": dose.group(1).strip() if dose else None,
                      "boericke_excerpt": re.sub(r"\s+", " ", body[:900]).strip(), "source": BOERICKE})
    cands.sort(key=lambda c: -c["books_mentioning"])
    (HERE / "staging").mkdir(exist_ok=True)
    (HERE / "staging/candidate_medicines.json").write_text(json.dumps({"candidates": cands, "skipped": skipped}, ensure_ascii=False, indent=1))
    print(f"headings={len(heads)} candidates={len(cands)} dup_existing={len(skipped['duplicate_existing'])} "
          f"dup_batch={len(skipped['duplicate_in_batch'])} uncorroborated={len(skipped['uncorroborated'])}")
    print([(c['name_en'], c['books_mentioning']) for c in cands[:70]])

main()
