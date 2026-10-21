"""Build the static site: an interactive transfer map plus the two gap lists.

Inputs:  data/processed/{patents,startups,spinoffs,edges_similarity,edges_known,
         orphan_technologies,researchless_startups,translations_en}.csv and config.yaml
         Italian texts are shown in their English machine translation (marked as such).
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


# ATECO 2007 divisions are the NACE Rev. 2 divisions: official English names
NACE = {
    "20": "Manufacture of chemicals and chemical products",
    "21": "Manufacture of basic pharmaceutical products and preparations",
    "22": "Manufacture of rubber and plastic products",
    "26": "Manufacture of computer, electronic and optical products",
    "27": "Manufacture of electrical equipment",
    "28": "Manufacture of machinery and equipment n.e.c.",
    "32": "Other manufacturing",
    "33": "Repair and installation of machinery and equipment",
    "62": "Computer programming, consultancy and related activities",
    "63": "Information service activities",
    "71": "Architectural and engineering activities; technical testing and analysis",
    "72": "Scientific research and development",
    "74": "Other professional, scientific and technical activities",
    "86": "Human health activities",
}


def clip(text, n):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def build_data():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    patents, startups, spinoffs = read("patents.csv"), read("startups.csv"), read("spinoffs.csv")
    sim, known = read("edges_similarity.csv"), read("edges_known.csv")
    orphans, researchless = read("orphan_technologies.csv"), read("researchless_startups.csv")
    orphan_info = orphans.set_index("patent_id")
    tr = read("translations_en.csv") if (PROCESSED / "translations_en.csv").exists() else pd.DataFrame(
        columns=["kind", "key", "text_en"])
    en = {kind: g.set_index("key")["text_en"].to_dict() for kind, g in tr.groupby("kind")}
    en_title, en_desc = (en.get(k, {}) for k in ("patent_title", "startup_description"))
    rl_ids = set(researchless["vat_number"])
    linked_spinoffs = set(known.loc[known["target_type"] == "spinoff", "target_id"]) | set(
        known.loc[known["source_type"] == "spinoff", "source_id"])

    nodes = []
    for r in patents.itertuples():
        o = orphan_info.loc[r.patent_id] if r.patent_id in orphan_info.index else None
        nodes.append({
            "id": "P:" + r.patent_id, "type": "patent", "ref": r.patent_id,
            "label": clip(en_title.get(r.patent_id) or (r.title.capitalize() if r.title.isupper() else r.title), 70),
            "mt": r.patent_id in en_title,
            "text": clip(r.abstract, 700) if r.abstract else "",
            "ipc": r.ipc_subclasses.split("|")[0] if r.ipc_subclasses else "",
            # Technology family for the map clusters: first medtech IPC subclass
            "group": (r.medtech_subclasses.split("|")[0] if r.medtech_subclasses else "A61B"),
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
            "text": clip(en_desc.get(r.vat_number, r.description), 500), "mt": r.vat_number in en_desc,
            "place": r.municipality.title(), "website": r.website,
            "sector": NACE.get(r.ateco[:2], ""),
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
            "repoUrl": (cfg.get("site") or {}).get("repo_url") or "",
            "model": cfg["embedding"]["model"],
            "startupList": startups["list_date"].iloc[0] if len(startups) else "",
            "built": date.today().isoformat(),
            "nPatents": len(patents),
            "nStartups": len(startups),
            "nStartupsText": int((startups["description"] != "").sum()),
            "nSpinoffsListed": len(spinoffs),
            "nAbstracts": int((patents["text_source"] == "abstract").sum()),
            "nAbstractsOps": int((patents["abstract_source"] == "epo_ops").sum()),
            "nTranslated": int(tr["kind"].eq("startup_description").sum()) if len(tr) else 0,
            "nByAteco": int(startups["match_reason"].str.startswith("ateco").sum()),
            **registry_counts(cfg),
            **calibration(sim),
        },
    }


def registry_counts(cfg):
    """Totals of the raw startup register, when the raw file is available locally."""
    csvs = sorted(Path("data/raw/startups").glob("startup_*.csv"))
    if not csvs:
        return {}
    raw = pd.read_csv(csvs[-1], sep="|", encoding="latin-1", dtype=str, keep_default_na=False)
    region = raw[[c for c in raw.columns if c.strip() == "regione"][0]].str.strip()
    return {"nItaly": len(raw), "nRegion": int(region.str.casefold().eq(cfg["startups"]["region"].casefold()).sum())}


def calibration(sim):
    """Precision and recall of the current threshold on the hand-labelled pairs."""
    path = Path("data/manual/calibration_pairs.csv")
    if not path.exists():
        return {}
    lab = pd.read_csv(path, dtype=str, keep_default_na=False)
    lab = lab[lab["label"].isin(["0", "1"])]
    predicted = set(zip(sim["tech_id"], sim["startup_id"]))
    pred = [(p, v) in predicted for p, v in zip(lab["patent_id"], lab["vat_number"])]
    y = lab["label"].eq("1").tolist()
    tp = sum(a and b for a, b in zip(pred, y))
    return {
        "calPairs": len(lab), "calPositive": sum(y),
        "calPrecision": round(tp / max(sum(pred), 1), 2), "calRecall": round(tp / max(sum(y), 1), 2),
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
