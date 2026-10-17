"""Merge abstracts into the `patents` table.

Usage:
    python src/clean/merge_abstracts.py data/processed/patents.csv data/raw/abstracts.json espacenet_page

`abstracts.json` is a list of {"family_id", "abstract", "lang"}. Patents without an
abstract fall back to their title for embeddings; `text_source` records which was used.
"""
import json
import sys

import pandas as pd


def main(patents_path, abstracts_path, source_label):
    patents = pd.read_csv(patents_path, dtype={"family_id": str})
    with open(abstracts_path, encoding="utf-8") as f:
        abstracts = pd.DataFrame(json.load(f))
    abstracts["family_id"] = abstracts["family_id"].astype(str).str.lstrip("0")
    abstracts = abstracts.drop_duplicates("family_id")

    patents = patents.drop(columns=[c for c in ["abstract", "abstract_lang", "abstract_source"] if c in patents])
    merged = patents.merge(
        abstracts.rename(columns={"lang": "abstract_lang"}), on="family_id", how="left"
    )
    merged["abstract"] = merged["abstract"].fillna("").str.strip()
    has_abs = merged["abstract"] != ""
    merged["abstract_source"] = has_abs.map({True: source_label, False: ""})
    merged["text_for_embedding"] = merged["abstract"].where(has_abs, merged["title"])
    merged["text_source"] = has_abs.map({True: "abstract", False: "title"})
    merged.to_csv(patents_path, index=False)

    unmatched = set(abstracts["family_id"]) - set(patents["family_id"])
    print(f"patents:              {len(merged)}")
    print(f"with abstract:        {has_abs.sum()}")
    print(f"title only:           {(~has_abs).sum()}")
    print(f"abstract languages:   {merged.loc[has_abs, 'abstract_lang'].value_counts().to_dict()}")
    print(f"unmatched in json:    {len(unmatched)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "espacenet_page")
