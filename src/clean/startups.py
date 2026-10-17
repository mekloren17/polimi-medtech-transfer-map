"""Build data/processed/startups.csv: Lombard medtech innovative startups.

Input: the newest data/raw/startups/startup_DDMMYYYY.csv (see src/collect/startups.py).
Filters, all set in config.yaml:
  1. region == Lombardia
  2. medtech = ATECO class in `ateco_codes` OR a keyword in the text (name + description)

The open-data list has no business description: only name, ATECO code and its division
label. Descriptions are merged from data/raw/startups/descriptions.csv
(columns: vat_number, description, description_source) when that file exists; until then
the keyword filter can only look at company names.

Usage:
    python src/clean/startups.py [--sample N]
"""
import argparse
import re
from pathlib import Path

import pandas as pd
import yaml

RAW_DIR = Path("data/raw/startups")
DESCRIPTIONS = RAW_DIR / "descriptions.csv"
OUT = Path("data/processed/startups.csv")

COLUMNS = {
    "denominazione": "name",
    "nat.giuridica": "legal_form",
    "codice fiscale": "vat_number",
    "pv": "province",
    "comune": "municipality",
    "regione": "region",
    "data iscrizione alla sezione delle startup": "registered_startup",
    "data inizio dell'esercizio effettivo dell'attività": "founded",
    "ateco 2007": "ateco",
    "attività": "ateco_division",
    "sito internet": "website",
    "possesso di brevetti": "owns_patents",
}


def load_registry():
    csvs = sorted(RAW_DIR.glob("startup_*.csv"), key=lambda p: pd.to_datetime(p.stem[-8:], format="%d%m%Y"))
    if not csvs:
        raise SystemExit("No startup_*.csv in data/raw/startups/: run src/collect/startups.py first.")
    path = csvs[-1]
    df = pd.read_csv(path, sep="|", encoding="latin-1", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.drop(columns=[c for c in df.columns if c == "" or c.startswith("Unnamed")])
    df = df.apply(lambda s: s.str.strip())
    return df, path


def keyword_pattern(keywords):
    # Each keyword must start a word; inner spaces match any whitespace.
    alternatives = [r"\s+".join(map(re.escape, k.lower().split())) for k in keywords]
    return re.compile(r"(?<!\w)(" + "|".join(alternatives) + ")", re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20, help="rows to print as a sample")
    args = parser.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["startups"]
    raw, path = load_registry()
    missing = set(COLUMNS) - set(raw.columns)
    if missing:
        raise SystemExit(f"Columns not found in {path.name}: {sorted(missing)}")
    df = raw[list(COLUMNS)].rename(columns=COLUMNS)
    list_date = pd.to_datetime(path.stem[-8:], format="%d%m%Y").date()

    # 6-digit ATECO code -> "32.50.11"
    df["ateco"] = df["ateco"].str.replace(r"^(\d{2})(\d{2})(\d{2})$", r"\1.\2.\3", regex=True)
    for col in ["founded", "registered_startup"]:
        df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    if DESCRIPTIONS.exists():
        desc = pd.read_csv(DESCRIPTIONS, dtype=str, keep_default_na=False)
        df = df.merge(desc[["vat_number", "description", "description_source"]], on="vat_number", how="left")
    else:
        df["description"] = ""
        df["description_source"] = ""
    df[["description", "description_source"]] = df[["description", "description_source"]].fillna("")

    n_italy = len(df)
    df = df[df["region"].str.casefold() == cfg["region"].casefold()].copy()
    n_region = len(df)

    by_ateco = df["ateco"].str[:5].isin(cfg["ateco_codes"])
    pattern = keyword_pattern(cfg["keywords"])
    text = (df["name"] + " " + df["description"]).str.lower()
    hits = text.apply(lambda t: sorted({m.lower() for m in pattern.findall(t)}))
    by_keyword = hits.str.len() > 0

    df["matched_keywords"] = hits.str.join("|")
    df["match_reason"] = (
        by_ateco.map({True: "ateco", False: ""}) + (by_ateco & by_keyword).map({True: "+", False: ""})
        + by_keyword.map({True: "keyword", False: ""})
    )
    df["is_polimi_spinoff"] = pd.NA  # filled once the spinoffs table exists
    df["list_date"] = list_date
    out = df[by_ateco | by_keyword].sort_values("name")
    out = out[[
        "vat_number", "name", "municipality", "province", "ateco", "ateco_division", "founded",
        "description", "description_source", "is_polimi_spinoff", "website", "owns_patents",
        "match_reason", "matched_keywords", "registered_startup", "list_date",
    ]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    n_desc = (df["description"] != "").sum()
    print(f"source list:              {path.name} ({list_date})")
    print(f"startups in Italy:        {n_italy}")
    print(f"in {cfg['region']}:            {n_region}")
    print(f"  with description:       {n_desc}")
    print(f"  ATECO {'/'.join(cfg['ateco_codes'])}:       {by_ateco.sum()}")
    print(f"  keyword match:          {by_keyword.sum()}  (on {'name + description' if n_desc else 'name only'})")
    print(f"  ATECO and keyword:      {(by_ateco & by_keyword).sum()}")
    print(f"medtech (union):          {len(out)} -> {OUT}")
    print("\ntop ATECO divisions among keyword-only matches:")
    print(df.loc[by_keyword & ~by_ateco, "ateco_division"].value_counts().head(8).to_string())
    if args.sample:
        print(f"\nsample of {min(args.sample, len(out))}:")
        sample = out.sample(min(args.sample, len(out)), random_state=0)
        for _, r in sample.iterrows():
            print(f"- [{r.match_reason}] {r['name']} | {r.ateco} {r.ateco_division} | {r.matched_keywords}")


if __name__ == "__main__":
    main()
