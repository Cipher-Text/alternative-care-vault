#!/usr/bin/env python3
"""Rank candidate symptoms/conditions by how widely the homeopathy corpus discusses them, and for each
find the remedies that Dewey (condition-indexed therapeutics) lists near it. Dedupes against existing
symptoms and aliases. Output: staging/candidate_symptoms.json"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, HERE, Registry, load_existing, norm

# term -> category (existing app categories). Terms are the vocabulary to look for in the corpus.
VOCAB = {
 "neurological": ["Migraine","Neuralgia","Sciatica","Epilepsy","Paralysis","Numbness","Tremors","Neuritis"],
 "respiratory": ["Whooping Cough","Croup","Pneumonia","Hoarseness","Pleurisy","Hay Fever","Dyspnea","Influenza","Tonsillitis","Laryngitis"],
 "digestive": ["Colic","Dysentery","Flatulence","Hemorrhoids","Gastritis","Heartburn","Vomiting","Gallstones","Hiccough","Worms","Cholera","Loss Of Appetite","Cholera Infantum"],
 "cardiovascular": ["Palpitation","Angina Pectoris","Varicose Veins","Dropsy"],
 "skin": ["Eczema","Boils","Urticaria","Herpes","Ringworm","Psoriasis","Itching","Burns","Wounds","Erysipelas","Chilblains","Abscess","Bed Sores","Dandruff"],
 "musculoskeletal": ["Rheumatism","Arthritis","Neck Pain","Cramps","Sprains","Fractures","Lameness"],
 "mental": ["Depression","Grief","Fear","Irritability","Hysteria","Restlessness","Forgetfulness","Anger"],
 "ear_nose_throat": ["Toothache","Conjunctivitis","Styes","Deafness","Catarrh","Nasal Polyps","Hoarseness","Sore Mouth","Tinnitus"],
 "urinary": ["Cystitis","Bed Wetting","Kidney Stones","Retention Of Urine","Incontinence","Prostatitis"],
 "reproductive": ["Leucorrhea","Amenorrhea","Menopause","Morning Sickness","Impotence","Morning Sickness","Sterility","Labor Pains"],
 "general": ["Debility","Convalescence","Teething","Dropsy","Emaciation","Night Sweats","Fainting","Colds In Children"],
 "immune": ["Measles","Mumps","Chickenpox","Scarlet Fever","Typhoid","Malaria","Diphtheria","Smallpox"],
 "metabolic": ["Obesity","Rickets","Anemia","Goitre"],
}
EXTRA_ALIASES = {"Hoarseness":["Aphonia"],"Dyspnea":["Dyspnoea","Breathlessness"],"Hemorrhoids":["Piles"],
 "Bed Wetting":["Enuresis"],"Whooping Cough":["Pertussis"],"Leucorrhea":["Leucorrhoea"],"Anemia":["Anaemia"],
 "Rheumatism":["Rheumatic Pain"],"Eczema":["Skin Eruption Eczema"],"Heartburn":["Pyrosis","Acidity"],
 "Palpitation":["Palpitations"],"Hiccough":["Hiccup","Hiccups"],"Goitre":["Goiter"],"Worms":["Worm Infestation"],
 "Dropsy":["Edema","Oedema"]}

def main():
    reg = Registry("symptoms", load_existing("symptoms"))
    for k, v in EXTRA_ALIASES.items():
        for x in v: reg.canon[norm(x)] = k
    texts = {}
    for p in sorted((ROOT / "processed/homeopathy").glob("*/book.json")):
        d = json.loads(p.read_text())
        if d.get("language", "en").lower().startswith(("bn", "beng")): continue
        texts[d["id"]] = norm(" ".join(pg["text"] for pg in d["pages"]))
    out, seen, dup = [], set(), []
    for cat, terms in VOCAB.items():
        for t in terms:
            canon, how = reg.lookup(t, fuzzy=0.93)
            key = norm(t)
            if canon and reg.is_existing(canon):
                dup.append({"term": t, "matches": canon, "via": how}); continue
            if key in seen: dup.append({"term": t, "matches": t, "via": "in-batch"}); continue
            seen.add(key)
            pat = re.compile(r'\b' + re.escape(key) + r'\b')
            per_book = {b: len(pat.findall(tx)) for b, tx in texts.items()}
            nb = sum(1 for n in per_book.values() if n)
            out.append({"name_en": t, "category": cat, "books_mentioning": nb, "total_mentions": sum(per_book.values())})
    out = [o for o in out if o["books_mentioning"] >= 6]
    out.sort(key=lambda o: -o["total_mentions"])
    (HERE / "staging").mkdir(exist_ok=True)
    (HERE / "staging/candidate_symptoms.json").write_text(json.dumps({"candidates": out, "skipped_duplicates": dup}, indent=1))
    print(len(out), "candidates;", len(dup), "dups:", [d["term"] + "→" + d["matches"] for d in dup])
    print([(o["name_en"], o["books_mentioning"]) for o in out])

main()
