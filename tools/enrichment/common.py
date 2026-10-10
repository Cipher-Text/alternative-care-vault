"""Shared helpers for the enrichment pipeline: name normalisation + duplicate detection."""
import difflib, json, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
HERE = Path(__file__).resolve().parent

def load_aliases():
    return json.loads((HERE / "aliases.json").read_text())

def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("oe", "e").replace("ae", "e")           # homoeopathic/homeopathic, diarrhoea/diarrhea
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

class Registry:
    """Maps any known name/alias/spelling variant to one canonical key."""
    def __init__(self, kind, records):
        self.kind = kind
        al = load_aliases().get(kind, {})
        self.canon = {}      # norm(any name) -> canonical display name
        for r in records:
            self.canon[norm(r["name_en"])] = r["name_en"]
        self.existing = set()     # canonical names that correspond to a record already in app/*.json
        for canonical, variants in al.items():
            group = [canonical, *variants]
            hit = [self.canon[norm(v)] for v in group if norm(v) in self.canon]
            if hit:                # group touches an existing record: collapse onto that record's name
                canonical = hit[0]
                self.existing.add(canonical)
            for v in group:
                self.canon[norm(v)] = canonical
        self.existing |= {r["name_en"] for r in records}
        # Latin binomials: first word alone ("Arnica") also resolves, if unambiguous
        first = {}
        for k, v in list(self.canon.items()):
            first.setdefault(k.split()[0], set()).add(v)
        self.first = {k: next(iter(v)) for k, v in first.items() if len(v) == 1}

    def lookup(self, name, fuzzy=0.9):
        k = norm(name)
        if k in self.canon: return self.canon[k], "exact"
        if k in self.first: return self.first[k], "first-word"
        m = difflib.get_close_matches(k, self.canon.keys(), n=1, cutoff=fuzzy)
        if m: return self.canon[m[0]], "fuzzy"
        return None, None

    def is_existing(self, canon):
        return canon in self.existing

    def add(self, name):
        self.canon[norm(name)] = name
        self.first.setdefault(norm(name).split()[0], name)

def load_existing(kind):
    f = "medicines" if kind == "medicines" else "symptoms"
    return json.loads((APP / f"{f}.json").read_text())[kind]
