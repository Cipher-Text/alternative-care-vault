#!/usr/bin/env python3
"""Combine hand-authored Ayurveda records (ayurveda_authored.py) with web notes into drafts_ayurveda.json (appended to
drafts_medicines_extra via drafts file consumed by merge.py) and provenance_ayurveda.json."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ayurveda_authored import D
S = Path(__file__).parent / "staging"
web = {}
for f in "ab":
    p = S / f"web_ayurveda_{f}.json"
    if p.exists(): web.update({x["name_en"]: x for x in json.loads(p.read_text())})
oush = {x["name_en"].lower(): x for x in json.loads((S / "oushadhi_formulations.json").read_text())}
# Cautions strengthened from the web safety notes (staging/web_ayurveda_*.json) where they add something material.
GUD = ("Guduchi products have been linked to herb-induced liver injury; avoid in autoimmune or liver disease and in pregnancy; may lower blood sugar",
       "গুলঞ্চজাত পণ্য যকৃতের ক্ষতির সাথে যুক্ত বলে রিপোর্ট আছে; অটোইমিউন বা যকৃতের রোগে ও গর্ভাবস্থায় এড়িয়ে চলুন; রক্তে শর্করা কমাতে পারে")
OVR = {
 "Guduchi Churna": GUD, "Maharasnadi Kashayam": GUD, "Guduchyadi Kashayam": GUD,
 "Nimbadi Kashayam": ("Neem may lower blood sugar and is traditionally avoided in pregnancy; contains guduchi, which has liver-injury reports",
                      "নিম রক্তে শর্করা কমাতে পারে ও গর্ভাবস্থায় ঐতিহ্যগতভাবে এড়ানো হয়; গুলঞ্চ থাকায় যকৃতের ক্ষতির রিপোর্ট আছে"),
 "Gokshura Churna": ("Safety is not established; rare liver toxicity has been suggested; avoid in pregnancy",
                     "নিরাপত্তা প্রতিষ্ঠিত নয়; বিরল ক্ষেত্রে যকৃতের বিষক্রিয়ার ইঙ্গিত আছে; গর্ভাবস্থায় এড়িয়ে চলুন"),
 "Vacha Churna": ("Contains beta-asarone, carcinogenic in animal studies; can cause vomiting; avoid high doses and in pregnancy",
                  "বিটা-অ্যাসারোন থাকে, যা প্রাণীদেহে ক্যান্সারজনক বলে পাওয়া গেছে; বমি হতে পারে; বেশি মাত্রা ও গর্ভাবস্থায় এড়িয়ে চলুন"),
 "Haridrakhanda": ("Contains sugar and iron bhasma; people with diabetes or iron overload should consult a physician; avoid in pregnancy unless supervised",
                   "চিনি ও লৌহ ভস্ম থাকে; ডায়াবেটিস বা আয়রন-আধিক্যে চিকিৎসকের পরামর্শ নিন; পরামর্শ ছাড়া গর্ভাবস্থায় এড়িয়ে চলুন"),
 "Triphaladi Taila": ("For external use only; the source lists galena (lead sulphide) as an ingredient, so use only authorised products",
                      "শুধু বাহ্যিক ব্যবহারের জন্য; উৎসে গ্যালেনা (সীসা সালফাইড) উপাদান হিসেবে উল্লিখিত, তাই অনুমোদিত পণ্যই ব্যবহার করুন"),
 "Kantakaryavaleha": ("Contains sugar; plumbago in the formula is an irritant and avoided in pregnancy; people with diabetes should consult a physician",
                      "চিনি থাকে; এতে থাকা চিতা গর্ভাবস্থায় পরিত্যাজ্য; ডায়াবেটিস রোগীরা চিকিৎসকের পরামর্শ নিন"),
 "Punarnava Churna": ("May add to the effect of diuretics and affect kidney function; consult a physician if on diuretics",
                      "মূত্রবর্ধক ওষুধের প্রভাব বাড়াতে ও কিডনির কাজে প্রভাব ফেলতে পারে; মূত্রবর্ধক ওষুধ চললে চিকিৎসকের পরামর্শ নিন"),
 "Dhanvantaram Gulika": ("Contains camphor; avoid in infants and in pregnancy unless supervised",
                         "কর্পূর থাকে; শিশু ও গর্ভাবস্থায় তত্ত্বাবধান ছাড়া এড়িয়ে চলুন"),
 "Shatavari Churna": ("Safety not well studied; avoid in pregnancy unless supervised; may affect blood sugar",
                      "নিরাপত্তা ভালোভাবে গবেষিত নয়; তত্ত্বাবধান ছাড়া গর্ভাবস্থায় এড়িয়ে চলুন; রক্তে শর্করাকে প্রভাবিত করতে পারে"),
}
drafts, prov = [], {}
for key, (name, bn, cat, de, db, ie, ib, den, dbn, cen, cbn) in D.items():
    r = {"name_en": name, "name_bn": bn, "system": "ayurveda", "category": cat, "description_en": de, "description_bn": db,
         "dosage_guidance_en": den, "dosage_guidance_bn": dbn, "indications_en": ie, "indications_bn": ib}
    if name in OVR: cen, cbn = OVR[name]
    if cen: r["contraindications_en"], r["contraindications_bn"] = cen, cbn
    drafts.append(r)
    w = web.get(key, {})
    prov[name] = {"oushadhi_name": key, "classical_reference": oush[key.lower()]["reference"], "ingredients": oush[key.lower()]["ingredients"],
                  "key_herbs": w.get("key_herbs"), "safety_note": w.get("safety_note"), "evidence_note": w.get("evidence_note"), "urls": w.get("urls")}
(S / "drafts_ayurveda.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=1))
(S / "provenance_ayurveda.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1))
print(len(drafts), "drafts;", sum(1 for v in prov.values() if v["urls"]), "with web provenance")
