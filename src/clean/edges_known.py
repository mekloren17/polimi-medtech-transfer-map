"""Build data/processed/edges_known.csv: verified links between Polimi and companies.

Relations, all from public sources:
  - spinoff -> startup   `same_company`  the startup's VAT number is that of an accredited
                                         Polimi spin-off (Polimi TTO page)
  - patent  -> spinoff   `co_applicant`  the spin-off is an applicant of the patent (EPO data)
  - patent  -> startup   `co_applicant`  the startup is an applicant of the patent (EPO data)
Organisation names are compared after normalisation (src/clean/names.py), whole name
against whole name, so "RESTECH S R L SPIN OFF DE POLITECNICO DI MILANO" matches "Restech S.r.l.".

Licences and informal collaborations are mostly not public, so a missing edge does not
prove the absence of a link.

Usage:
    python src/clean/edges_known.py
"""
from pathlib import Path

import pandas as pd

from names import org_key

PROCESSED = Path("data/processed")
OUT = PROCESSED / "edges_known.csv"
COLUMNS = ["source_id", "source_type", "target_id", "target_type", "relation", "evidence"]


def read(name):
    return pd.read_csv(PROCESSED / name, dtype=str, keep_default_na=False)


def main():
    patents, startups, spinoffs = read("patents.csv"), read("startups.csv"), read("spinoffs.csv")
    edges = []

    # spin-off <-> startup: same legal entity
    in_startups = set(startups["vat_number"])
    for r in spinoffs[spinoffs["vat_number"].isin(in_startups)].itertuples():
        edges.append((r.spinoff_id, "spinoff", r.vat_number, "startup", "same_company", r.evidence))

    # patent <-> spin-off / startup: co-applicant
    spinoff_by_key = {org_key(n): sid for n, sid in zip(spinoffs["name"], spinoffs["spinoff_id"])}
    startup_by_key = {org_key(n): vat for n, vat in zip(startups["name"], startups["vat_number"])}
    for r in patents.itertuples():
        applicants = {org_key(a) for a in r.applicants.split("|") if a}
        for key in sorted(applicants):
            evidence = f"EPO applicants of {r.patent_id}"
            if key in spinoff_by_key:
                edges.append((r.patent_id, "patent", spinoff_by_key[key], "spinoff", "co_applicant", evidence))
            if key in startup_by_key:
                edges.append((r.patent_id, "patent", startup_by_key[key], "startup", "co_applicant", evidence))

    out = pd.DataFrame(edges, columns=COLUMNS).drop_duplicates()
    out.to_csv(OUT, index=False)
    print(f"known edges:   {len(out)}")
    print(out.groupby(["source_type", "target_type", "relation"]).size().to_string())
    print(f"saved:         {OUT}")


if __name__ == "__main__":
    main()
