"""Derive the gap views from similarity and known edges.

Outputs:
  data/processed/orphan_technologies.csv
      Patents with no known link to a spin-off or startup (edges_known) and no Lombard
      startup at or above the similarity threshold. Sorted by best score, so the top rows
      are near misses and the bottom rows the most isolated technologies.
      `industry_co_applicants` lists company co-applicants (e.g. a medical device maker):
      those technologies are not orphan in the transfer sense, only unmatched to startups.
  data/processed/researchless_startups.csv
      Lombard startups with at least one patent at or above the threshold but no known link
      to Polimi (not a Polimi spin-off, not a co-applicant of a Polimi patent).
      `only_low_confidence` is True when every match comes from a title-only patent.

Startups without a description were not embedded, so they cannot appear in either view.

Usage:
    python src/score/gaps.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROCESSED = Path("data/processed")
# Applicant names with a company legal form (universities, hospitals, foundations excluded)
COMPANY = re.compile(r"\b(S ?R ?L|S ?P ?A|SRL|SPA|INC|CORP|GMBH|LTD|N ?V|B ?V|AG|SA|CO)\b")
# Private hospitals are often SpA: not an industrial partner
NOT_INDUSTRY = re.compile(r"\b(UNIV|FOND|IRCCS|OSPEDAL|POLICLINICO|HUMANITAS|CENTRO CARDIOLOGICO)")


def industry_applicants(co_applicants):
    """Company co-applicants: the technology already has an industrial partner."""
    names = [a for a in co_applicants.split("|") if a]
    return "|".join(a for a in names if COMPANY.search(a) and not NOT_INDUSTRY.search(a))


def read(name):
    return pd.read_csv(PROCESSED / name, dtype=str, keep_default_na=False)


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    threshold = cfg["similarity"]["threshold"]
    model = cfg["embedding"]["model"]
    emb_dir = PROCESSED / "embeddings" / model.split("/")[-1]

    patents, startups = read("patents.csv"), read("startups.csv")
    known, sim_edges = read("edges_known.csv"), read("edges_similarity.csv")
    sim_edges["score"] = sim_edges["score"].astype(float)
    sim_edges["low_confidence"] = sim_edges["low_confidence"] == "True"

    # Best startup for every patent, also below threshold (needs the full score matrix)
    pe = pd.read_parquet(emb_dir / "patents.parquet")
    se = pd.read_parquet(emb_dir / "startups.parquet")
    sim = np.vstack(pe["embedding"].to_numpy()) @ np.vstack(se["embedding"].to_numpy()).T
    best = pd.DataFrame({
        "patent_id": pe["id"],
        "best_score": sim.max(axis=1).round(4),
        "best_startup_id": se["id"].to_numpy()[sim.argmax(axis=1)],
    })
    names = startups.set_index("vat_number")["name"]

    # Orphan technologies
    linked_patents = set(known.loc[known["source_type"] == "patent", "source_id"])
    orphans = patents.merge(best, on="patent_id")
    orphans = orphans[~orphans["patent_id"].isin(linked_patents) & (orphans["best_score"] < threshold)]
    orphans = orphans.assign(
        industry_co_applicants=orphans["co_applicants"].map(industry_applicants),
        best_startup_name=orphans["best_startup_id"].map(names),
        low_confidence=orphans["text_source"] == "title",
        threshold=threshold,
        model=model,
    )[["patent_id", "family_id", "title", "priority_date", "ipc_subclasses", "applicants",
       "industry_co_applicants", "text_source", "low_confidence", "best_score", "best_startup_id", "best_startup_name", "threshold", "model"]]
    orphans = orphans.sort_values("best_score", ascending=False)
    orphans.to_csv(PROCESSED / "orphan_technologies.csv", index=False)

    # Research-less startups
    connected = set(startups.loc[startups["is_polimi_spinoff"] == "True", "vat_number"])
    connected |= set(known.loc[known["target_type"] == "startup", "target_id"])
    titles = patents.set_index("patent_id")["title"]
    rows = []
    for vat, g in sim_edges.groupby("startup_id"):
        if vat in connected:
            continue
        top = g.sort_values("score", ascending=False).iloc[0]
        rows.append({
            "vat_number": vat,
            "name": names.get(vat, ""),
            "n_matches": len(g),
            "n_matches_high_confidence": int((~g["low_confidence"]).sum()),
            "only_low_confidence": bool(g["low_confidence"].all()),
            "best_patent_id": top["tech_id"],
            "best_patent_title": titles.get(top["tech_id"], ""),
            "best_score": top["score"],
            "top_terms": top["top_terms"],
            "threshold": threshold,
            "model": model,
        })
    researchless = pd.DataFrame(rows).sort_values(["only_low_confidence", "best_score"], ascending=[True, False])
    researchless.to_csv(PROCESSED / "researchless_startups.csv", index=False)

    n_embedded = len(se)
    print(f"threshold {threshold}, model {model}")
    print(f"patents:                      {len(patents)}")
    print(f"  with a known link:          {len(linked_patents)}")
    print(f"  with a startup >= threshold: {sim_edges['tech_id'].nunique()}")
    print(f"  orphan technologies:        {len(orphans)}  (title only: {orphans['low_confidence'].sum()}, "
          f"with an industrial co-applicant: {(orphans['industry_co_applicants'] != '').sum()})")
    print(f"startups (with description):  {n_embedded} of {len(startups)}")
    print(f"  Polimi-connected:           {len(connected)}")
    print(f"  with a patent >= threshold: {sim_edges['startup_id'].nunique()}")
    print(f"  research-less:              {len(researchless)}  "
          f"(only low-confidence matches: {researchless['only_low_confidence'].sum()})")


if __name__ == "__main__":
    main()
