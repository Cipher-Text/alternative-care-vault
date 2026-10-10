#!/usr/bin/env python3
"""Fetch the proofread online Boericke remedy pages (materiamedica.info) that correct_ocr_lexicon.py uses as its reference.

  python3 tools/enrichment/fetch_reference_pages.py --out <dir>        # ~620 pages, ~8 min, 3 parallel, polite delay

Not committed to the repo (third-party site, regenerable). Re-running skips pages already present."""
import argparse, concurrent.futures, re, subprocess, time
from pathlib import Path
BASE = "https://www.materiamedica.info"
UA = "Mozilla/5.0 (research; care-vault proofreading)"

def get(url):
    return subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, url], capture_output=True, text=True).stdout

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    idx = get(f"{BASE}/en/materia-medica/william-boericke/index")
    # the index uses single-quoted hrefs; each remedy is /en/materia-medica/william-boericke/<slug>
    slugs = sorted(set(re.findall(r"href='/en/materia-medica/william-boericke/([a-z0-9\-]+)'", idx)) - {"index"})
    print(f"{len(slugs)} remedy pages")
    def one(slug):
        f = out / f"{slug}.html"
        if f.exists() and f.stat().st_size > 2000: return
        html = get(f"{BASE}/en/materia-medica/william-boericke/{slug}")
        if len(html) > 2000: f.write_text(html)
        time.sleep(0.5)
    with concurrent.futures.ThreadPoolExecutor(a.workers) as ex: list(ex.map(one, slugs))
    print("done:", len(list(out.glob('*.html'))), "pages in", out)
main()
