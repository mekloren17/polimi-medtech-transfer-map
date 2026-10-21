"""Build the static site: an interactive transfer map plus the two gap lists.

Inputs:  data/processed/{patents,startups,spinoffs,edges_similarity,edges_known,
         orphan_technologies,researchless_startups}.csv and config.yaml
Outputs: site/index.html             full page for GitHub Pages
         --fragment PATH (optional)  the same page without <html>/<head>/<body>, for hosts
                                     that wrap the page themselves (e.g. a Claude artifact)

All data is embedded in the page as JSON; the only external resources are d3 (cdnjs) and
Google Fonts. Only organisation-level fields are included.

Usage:
    python src/build/site.py [--fragment PATH]
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

PROCESSED = Path("data/processed")
TEMPLATE = Path(__file__).with_name("template.html")
OUT = Path("site/index.html")
LEGAL = re.compile(
    r"[\s,]*(S\.?R\.?L\.?S?|S\.?P\.?A\.?|SOCIETA'? (A RESPONSABILITA'? LIMITATA( SEMPLIFICATA)?|BENEFIT)"
    r"( A RESPONSABILITA'? LIMITATA)?|SB|LDA|B\.V\.|S\.T\.P\.)\b.*$",
    re.IGNORECASE,
)


def read(name):
    return pd.read_csv(PROCESSED / name, dtype=str, keep_default_na=False)


def short_name(name):
    """'ARMI S.R.L. SOCIETA' BENEFIT' -> 'Armi'; keeps names that are already mixed case."""
    base = LEGAL.sub("", name).strip(" .,-") or name
    return base.title() if base.isupper() and len(base) > 4 else base


def clip(text, n):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def build_data():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    patents, startups, spinoffs = read("patents.csv"), read("startups.csv"), read("spinoffs.csv")
    sim, known = read("edges_similarity.csv"), read("edges_known.csv")
    orphans, researchless = read("orphan_technologies.csv"), read("researchless_startups.csv")
    orphan_info = orphans.set_index("patent_id")
    rl_ids = set(researchless["vat_number"])
    linked_spinoffs = set(known.loc[known["target_type"] == "spinoff", "target_id"]) | set(
        known.loc[known["source_type"] == "spinoff", "source_id"])

    nodes = []
    for r in patents.itertuples():
        o = orphan_info.loc[r.patent_id] if r.patent_id in orphan_info.index else None
        nodes.append({
            "id": "P:" + r.patent_id, "type": "patent", "ref": r.patent_id,
            "label": clip(r.title.capitalize() if r.title.isupper() else r.title, 70),
            "text": clip(r.abstract, 700) if r.abstract else "",
            "ipc": r.ipc_subclasses.split("|")[0] if r.ipc_subclasses else "",
            "ipcAll": r.ipc_subclasses.replace("|", " · "),
            "priority": r.priority_date[:4],
            "applicants": r.applicants.replace("|", " · "),
            "titleOnly": r.text_source == "title",
            "orphan": o is not None,
            "industry": (o["industry_co_applicants"].replace("|", " · ") if o is not None else ""),
            "best": float(o["best_score"]) if o is not None else None,
            "bestStartup": ("S:" + o["best_startup_id"]) if o is not None else None,
        })
    for r in startups.itertuples():
        nodes.append({
            "id": "S:" + r.vat_number, "type": "startup", "ref": r.vat_number,
            "label": short_name(r.name), "legal": r.name,
            "text": clip(r.description, 500), "place": r.municipality.title(),
            "website": r.website, "sector": r.ateco_division[2:].strip().capitalize(),
            "founded": r.founded[:4], "spinoff": r.is_polimi_spinoff == "True",
            "researchless": r.vat_number in rl_ids, "noText": r.description == "",
        })
    for r in spinoffs.itertuples():
        if r.is_medtech != "True" and r.spinoff_id not in linked_spinoffs:
            continue
        nodes.append({
            "id": "X:" + r.spinoff_id, "type": "spinoff", "ref": r.spinoff_id,
            "label": short_name(r.name), "legal": r.name, "text": clip(r.description, 500),
            "founded": r.founded, "website": r.website, "evidence": r.evidence,
        })

    prefix = {"patent": "P:", "startup": "S:", "spinoff": "X:"}
    links = [{
        "source": "P:" + r.tech_id, "target": "S:" + r.startup_id, "kind": "similarity",
        "score": float(r.score), "low": r.low_confidence == "True", "terms": r.top_terms.split("|"),
    } for r in sim.itertuples()]
    links += [{
        "source": prefix[r.source_type] + r.source_id, "target": prefix[r.target_type] + r.target_id,
        "kind": "known", "relation": r.relation, "evidence": r.evidence,
    } for r in known.itertuples()]
    ids = {n["id"] for n in nodes}
    links = [link for link in links if link["source"] in ids and link["target"] in ids]

    return {
        "nodes": nodes,
        "links": links,
        "orphans": orphans["patent_id"].tolist(),
        "researchless": researchless["vat_number"].tolist(),
        "meta": {
            "threshold": cfg["similarity"]["threshold"],
            "model": cfg["embedding"]["model"],
            "startupList": startups["list_date"].iloc[0] if len(startups) else "",
            "built": date.today().isoformat(),
            "nPatents": len(patents),
            "nStartups": len(startups),
            "nStartupsText": int((startups["description"] != "").sum()),
            "nSpinoffsListed": len(spinoffs),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fragment", type=Path, help="also write the page without html/head/body")
    args = parser.parse_args()

    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    fragment = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)

    head, _, body = fragment.partition("<!--/HEAD-->")
    page = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{head}</head>\n<body>\n{body}</body>\n</html>\n"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    if args.fragment:
        args.fragment.write_text(fragment, encoding="utf-8")

    n_by_type = pd.Series([n["type"] for n in data["nodes"]]).value_counts().to_dict()
    n_by_kind = pd.Series([link["kind"] for link in data["links"]]).value_counts().to_dict()
    print(f"nodes: {n_by_type}")
    print(f"links: {n_by_kind}")
    print(f"page:  {OUT} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
