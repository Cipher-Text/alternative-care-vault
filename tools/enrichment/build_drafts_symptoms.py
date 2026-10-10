#!/usr/bin/env python3
"""Combine web facts (web_symptoms.json) + hand-written Bengali (bn_symptoms.json) into drafts_symptoms.json."""
import json
from pathlib import Path
S = Path(__file__).parent / "staging"
web = json.loads((S / "web_symptoms.json").read_text())
bn = json.loads((S / "bn_symptoms.json").read_text())
out = []
for w in web:
    n = w["name_en"]
    d = {"name_en": n, "description_en": w["description_en"].rstrip("."), "category": w["category"]}
    if n in bn:
        d["name_bn"], d["description_bn"] = bn[n]
    out.append(d)          # entries without Bengali fail merge validation on purpose (Debility = duplicate of Fatigue)
(S / "drafts_symptoms.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(len(out))
