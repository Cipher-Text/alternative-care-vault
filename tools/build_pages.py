#!/usr/bin/env python3
"""Stage only the static site and book assets referenced by its catalogue."""
import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def copy_asset(relative_path: str, destination: Path) -> None:
    source = (ROOT / relative_path).resolve()
    if ROOT not in source.parents:
        raise ValueError(f"Asset path escapes repository: {relative_path}")
    if not source.is_file():
        raise FileNotFoundError(f"Missing site asset: {relative_path}")
    target = destination / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build(output: Path) -> None:
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Choose an output directory outside the repository root")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for filename in ("index.html", "style.css", "app.js", "README.md"):
        shutil.copy2(ROOT / filename, output / filename)

    catalogue_path = ROOT / "processed/catalogue.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    copy_asset("processed/catalogue.json", output)
    for book in catalogue:
        for key in ("processed_json", "processed_epub"):
            asset = book.get(key)
            if asset:
                copy_asset(asset, output)

    total_size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    print(f"Staged {len(catalogue)} books in {output} ({total_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/care-vault-pages"))
    args = parser.parse_args()
    build(args.out)
