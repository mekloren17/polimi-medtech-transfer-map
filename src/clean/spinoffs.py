"""Build data/processed/spinoffs.csv from the Polimi spin-off pages.

Input: data/raw/polimi_spinoffs.json (src/collect/polimi_spinoffs.py) and the newest
startup registry list in data/raw/startups/ for the VAT number.

The VAT number (codice fiscale) is found by matching the spin-off to the innovative-startup
registry by website domain, then by normalised name. Spin-offs older than the registry's
5-year window are not in it, so their VAT number stays empty.
`is_medtech` uses the same keywords as the startup filter (config.yaml) on field, activity,
services and target market. The originating department is not published, so `department`
is empty.

Usage:
    python src/clean/spinoffs.py
"""
import json
import re
from pathlib import Path

import pandas as pd
import yaml

from names import domain_key, org_key

RAW = Path("data/raw/polimi_spinoffs.json")
RAW_DIR = Path("data/raw/startups")
OUT = Path("data/processed/spinoffs.csv")


def load_registry():
    csvs = sorted(RAW_DIR.glob("startup_*.csv"), key=lambda p: pd.to_datetime(p.stem[-8:], format="%d%m%Y"))
    df = pd.read_csv(csvs[-1], sep="|", encoding="latin-1", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda s: s.str.strip())
    return pd.DataFrame({
        "vat_number": df["codice fiscale"],
        "name_key": df["denominazione"].map(org_key),
        "domain": df["sito internet"].map(domain_key),
    })


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["startups"]
    raw = pd.DataFrame(json.load(open(RAW, encoding="utf-8"))).fillna("")
    registry = load_registry()

    df = pd.DataFrame({
        "spinoff_id": raw["slug"],
        "name": raw["legal_name"].where(raw["legal_name"] != "", raw["name"]),
        "founded": raw["founded_year"].str.extract(r"((?:19|20)\d{2})", expand=False).fillna(""),
        "department": "",
        "field": raw["field"],
        "description": (raw["activity"] + " " + raw["services"] + " Target market: " + raw["target_market"])
            .str.replace(r"\s*Target market:\s*$", "", regex=True).str.strip(),
        "website": raw["website"],
        "evidence": raw["url"],
    })

    by_domain = registry[registry["domain"] != ""].drop_duplicates("domain").set_index("domain")["vat_number"]
    by_name = registry.drop_duplicates("name_key").set_index("name_key")["vat_number"]
    domains = df["website"].map(domain_key)
    keys = df["name"].map(org_key)
    vat_domain = domains.map(by_domain)
    vat_name = keys.map(by_name)
    df["vat_number"] = vat_domain.fillna(vat_name).fillna("")
    df["vat_match"] = vat_domain.notna().map({True: "website", False: ""}).where(
        vat_domain.notna(), vat_name.notna().map({True: "name", False: ""})
    )

    pattern = re.compile(
        r"(?<!\w)(" + "|".join(r"\s+".join(map(re.escape, k.lower().split())) for k in cfg["keywords"]) + ")",
        re.IGNORECASE,
    )
    text = (raw["field"] + " " + raw["activity"] + " " + raw["services"] + " " + raw["target_market"]).str.lower()
    df["medtech_keywords"] = text.map(lambda t: "|".join(sorted({m.lower() for m in pattern.findall(t)})))
    df["is_medtech"] = df["medtech_keywords"] != ""

    df = df[["spinoff_id", "name", "vat_number", "vat_match", "founded", "department", "field",
             "description", "is_medtech", "medtech_keywords", "website", "evidence"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    print(f"spin-offs:                 {len(df)}")
    print(f"VAT found in registry:     {(df['vat_number'] != '').sum()}  {df['vat_match'].value_counts().to_dict()}")
    print(f"medtech (keywords):        {df['is_medtech'].sum()}")
    print(f"saved:                     {OUT}")


if __name__ == "__main__":
    main()
