"""Merge abstracts into the `patents` table.

Usage:
    python src/clean/merge_abstracts.py data/processed/patents.csv SOURCE [SOURCE ...]

Each SOURCE is `path.json=label`, in priority order: a family takes its abstract from the
first source that has one. Example (OPS first, Espacenet page extracts as fallback):
    python src/clean/merge_abstracts.py data/processed/patents.csv \
        data/raw/ops_abstracts.json=epo_ops data/raw/abstracts.json=espacenet_page

Each json is a list of {"family_id", "abstract", "lang"} (optionally "source_publication").
Patents without an abstract fall back to their title for embeddings; `text_source` records
which was used and `abstract_source` which source provided the abstract.
"""
import json
import sys

import pandas as pd

ABSTRACT_COLUMNS = ["abstract", "abstract_lang", "abstract_source", "abstract_publication"]


def read_source(spec):
    path, _, label = spec.rpartition("=")
    if not path:
        raise SystemExit(f"Source must be path.json=label, got: {spec}")
    with open(path, encoding="utf-8") as f:
        df = pd.DataFrame(json.load(f))
    df["family_id"] = df["family_id"].astype(str).str.lstrip("0")
    df["abstract"] = df["abstract"].fillna("").str.strip()
    df = df[df["abstract"] != ""].drop_duplicates("family_id")
    if "source_publication" not in df:
        df["source_publication"] = ""
    return df.assign(abstract_source=label).rename(
        columns={"lang": "abstract_lang", "source_publication": "abstract_publication"}
    )[["family_id"] + ABSTRACT_COLUMNS], label


def main(patents_path, specs):
    patents = pd.read_csv(patents_path, dtype={"family_id": str})
    patents = patents.drop(columns=[c for c in ABSTRACT_COLUMNS if c in patents])

    sources = [read_source(s) for s in specs]
    combined = pd.concat([df for df, _ in sources]).drop_duplicates("family_id", keep="first")
    merged = patents.merge(combined, on="family_id", how="left")
    for col in ABSTRACT_COLUMNS:
        merged[col] = merged[col].fillna("")
    has_abs = merged["abstract"] != ""
    merged["text_for_embedding"] = merged["abstract"].where(has_abs, merged["title"])
    merged["text_source"] = has_abs.map({True: "abstract", False: "title"})
    merged.to_csv(patents_path, index=False)

    print(f"patents:              {len(merged)}")
    for df, label in sources:
        used = (merged["abstract_source"] == label).sum()
        unmatched = len(set(df["family_id"]) - set(patents["family_id"]))
        print(f"  {label:18} available: {len(df):4}  used: {used:4}  unmatched families: {unmatched}")
    print(f"with abstract:        {has_abs.sum()}")
    print(f"title only:           {(~has_abs).sum()}")
    print(f"abstract languages:   {merged.loc[has_abs, 'abstract_lang'].value_counts().to_dict()}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
