#!/usr/bin/env python3
"""Combine hand-authored Unani records (unani_authored.py) + monograph fields + web notes into drafts_unani.json
and provenance_unani.json (incl. identity/term-meaning confidence flags)."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from unani_authored import D
S = Path(__file__).parent / "staging"
mono = {x["name_en"]: x for x in json.loads((S / "unani_monographs.json").read_text())}
web = {}
for f in "ab": web.update({x["name_en"]: x for x in json.loads((S / f"web_unani_{f}.json").read_text())})
def cat(w):
    c = (w or {}).get("category_unani")
    if not c: return "Mufrad Dawa"            # simple (single) drug, when no action class is documented
    return re.sub(r"\s*\(.*?\)", "", re.split(r"[;,](?![^(]*\))", c)[0]).strip() or "Mufrad Dawa"
def fmt_dose(d):
    d = re.sub(r"\bgm?\.?\b", "g", d.strip().rstrip("."), flags=re.I)
    return d
drafts, prov = [], {}
for key, (name, bn, bot, de, db, ie, ib, cen, cbn, dose) in D.items():
    m, w = mono[key], web.get(key, {})
    if dose: den, dbn = dose
    else:
        d = fmt_dose(m["dose"] or "")
        den = f"{d} of the dried drug, as directed by a Unani physician"
        dbn = f"{d} শুকনো ওষুধ, ইউনানি চিকিৎসকের নির্দেশ অনুযায়ী"
    r = {"name_en": name, "name_bn": bn, "system": "unani", "category": cat(w), "description_en": de, "description_bn": db,
         "dosage_guidance_en": den, "dosage_guidance_bn": dbn, "indications_en": ie, "indications_bn": ib}
    if bot: r["botanical_name"] = bot
    if cen: r["contraindications_en"], r["contraindications_bn"] = cen, cbn
    drafts.append(r)
    prov[name] = {"monograph_part": m["part"], "monograph_botanical": m["botanical"], "web_botanical": w.get("botanical_name"),
                  "family": w.get("family"), "uses_terms": w.get("uses_modern"), "safety_note": w.get("safety_note"),
                  "evidence_note": w.get("evidence_note"), "urls": w.get("urls"),
                  "needs_verification": key in ("Qust", "Kulthi", "Pambadana", "Tagar", "Behman Surkh", "Khiyarzah", "Chanbeli", "Qirfa")}
(S / "drafts_unani.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=1))
(S / "provenance_unani.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1))
print(len(drafts), "drafts")
for r in drafts[:3] + [x for x in drafts if x["name_en"] in ("Kaner","Kamila")]: print(r["name_en"], "|", r["category"], "|", r["dosage_guidance_en"])
