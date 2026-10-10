#!/usr/bin/env python3
"""Combine hand-authored text (medicines_authored.py) with web facts into drafts_medicines.json;
write per-remedy provenance (urls, evidence/safety notes, unverified flags) to staging/provenance_medicines.json."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from medicines_authored import D
S = Path(__file__).parent / "staging"
web = {x["name_en"]: x for f in "ab" for x in json.loads((S / f"web_medicines_{f}.json").read_text())}
SAFE_EN = "; use 30C or higher, avoid low potencies or mother tincture except under a practitioner"
SAFE_BN = "; 30C বা উচ্চতর পোটেনসি ব্যবহার করুন, চিকিৎসক ছাড়া নিম্ন পোটেনসি বা মূল টিংচার নয়"
drafts, prov = [], {}
for name, (bn, pot, de, db, ie, ib, toxic, dose) in D.items():
    w = web[name]
    en, bnd = dose or ("3-5 globules 2-3 times daily", "দিনে 2-3 বার 3-5 টি গোলক")
    if toxic and not dose: en, bnd = en + SAFE_EN, bnd + SAFE_BN
    drafts.append({"name_en": name, "name_bn": bn, "system": "homeopathy", "category": w["category"],
                   "description_en": de, "description_bn": db, "potency": pot,
                   "dosage_guidance_en": en, "dosage_guidance_bn": bnd, "indications_en": ie, "indications_bn": ib})
    prov[name] = {"source_en": w["source_en"], "common_names": w.get("common_names"), "safety_note": w.get("safety_note"),
                  "evidence_note": w.get("evidence_note"), "urls": w.get("urls")}
assert set(D) == set(json.loads((S / "selection.json").read_text())["medicines"]), "selection mismatch"
(S / "drafts_medicines.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=1))
(S / "provenance_medicines.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1))
print(len(drafts))
