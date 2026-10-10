#!/usr/bin/env python3
"""Merge reviewed drafts (staging/drafts_<kind>.json) into app/<kind>.json without creating duplicates.

  python3 tools/enrichment/merge.py medicines|symptoms [--apply]

Rules: a draft that resolves (name, alias, spelling variant, fuzzy) to an existing record is NEVER added;
only its EMPTY fields are filled in (existing values are never overwritten). Drafts duplicating each other
are collapsed. Records are validated against the schema before writing. Without --apply it only reports."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import APP, HERE, Registry, load_existing

REQUIRED = {
    "medicines": ["name_en", "name_bn", "system", "category", "description_en", "description_bn",
                  "potency", "dosage_guidance_en", "dosage_guidance_bn", "indications_en", "indications_bn"],
    "symptoms": ["name_en", "name_bn", "description_en", "description_bn", "category"],
}
SYSTEMS = {"homeopathy", "ayurveda", "unani", "herbal"}
SYM_CATS = {"neurological", "respiratory", "digestive", "musculoskeletal", "mental", "skin", "ear_nose_throat",
            "general", "immune", "cardiovascular", "metabolic", "reproductive", "urinary"}

def validate(kind, r):
    req = [k for k in REQUIRED[kind] if not (kind == "medicines" and k == "potency" and r.get("system") != "homeopathy")]
    errs = [f"missing {k}" for k in req if not str(r.get(k, "")).strip()]
    if kind == "medicines" and r.get("system") not in SYSTEMS: errs.append(f"bad system {r.get('system')!r}")
    if kind == "symptoms" and r.get("category") not in SYM_CATS: errs.append(f"bad category {r.get('category')!r}")
    return errs

def main():
    kind = sys.argv[1]; apply = "--apply" in sys.argv
    path = APP / f"{kind}.json"
    existing = json.loads(path.read_text())[kind]
    name = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--drafts=")), f"drafts_{kind}.json")
    drafts = json.loads((HERE / "staging" / name).read_text())
    def reg_for(system):
        # same tradition only; 'herbal' is a system-agnostic bucket that collides with any non-homeopathic herb
        ok = (lambda r: True) if kind == "symptoms" else (
            (lambda r: r["system"] in (system, "herbal") or (system == "herbal" and r["system"] != "homeopathy")))
        return Registry(kind, [r for r in existing if ok(r)])
    by_name = {r["name_en"]: r for r in existing}
    added, filled, dups, invalid = [], [], [], []
    for d in drafts:
        reg = reg_for(d.get("system"))
        canon, how = reg.lookup(d["name_en"])
        if canon and reg.is_existing(canon) and canon in by_name:                         # duplicate of a record we hold
            cur = by_name[canon]
            for k, v in d.items():
                if v not in (None, "", []) and cur.get(k) in (None, "", []):
                    cur[k] = v; filled.append((canon, k))
            dups.append((d["name_en"], canon, how)); continue
        errs = validate(kind, d)
        if errs: invalid.append((d.get("name_en"), errs)); continue
        d.setdefault("is_global", True); d.setdefault("is_active", True)
        existing.append(d); by_name[d["name_en"]] = d
        added.append(d["name_en"])
    for d in existing: d.pop("_aliases", None)
    print(f"{kind}: +{len(added)} new, {len(dups)} duplicates skipped, {len(filled)} empty fields filled, {len(invalid)} invalid")
    for x in dups: print("  dup:", x)
    for x in invalid: print("  invalid:", x)
    if apply:
        path.write_text(json.dumps({kind: existing}, ensure_ascii=False, indent=2) + "\n")
        print("written", path)
main()
