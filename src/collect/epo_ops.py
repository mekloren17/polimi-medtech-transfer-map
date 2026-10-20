"""Download patent abstracts from EPO Open Patent Services (OPS), reproducibly.

For every family in data/processed/patents.csv, one request to the INPADOC family
endpoint with the `biblio` constituent returns all family members with their abstracts.
We keep one abstract per family, preferring English, then Italian, then any language,
and the earliest-published member within the chosen language.

Credentials: a .env file in the project root (never committed) with
    OPS_KEY=...
    OPS_SECRET=...
(Consumer Key / Consumer Secret of an app at https://developers.epo.org).

Outputs (not committed, raw data):
    data/raw/ops/family_<family_id>.json   raw responses, used as a cache
    data/raw/ops_abstracts.json            [{"family_id", "abstract", "lang", "source_publication"}]
Then merge into the patents table with src/clean/merge_abstracts.py.

The python-epo-ops-client throttling middleware keeps requests within the fair-use limits
that OPS announces in every response.

Usage:
    python src/collect/epo_ops.py [--refresh]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

# This file is named like the client library: drop its own folder from the import path
# so that `import epo_ops` loads the library, not this script.
sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
import epo_ops  # noqa: E402
import pandas as pd
import requests

PATENTS = Path("data/processed/patents.csv")
CACHE = Path("data/raw/ops")
OUT = Path("data/raw/ops_abstracts.json")
LANG_PREFERENCE = ["en", "it"]


def credentials():
    env = Path(".env")
    if not env.exists():
        raise SystemExit("Missing .env with OPS_KEY and OPS_SECRET (see the docstring).")
    values = dict(
        line.split("=", 1) for line in env.read_text(encoding="utf-8-sig").splitlines() if "=" in line
    )
    try:
        return values["OPS_KEY"].strip(), values["OPS_SECRET"].strip()
    except KeyError:
        raise SystemExit(".env must define OPS_KEY and OPS_SECRET.")


def as_list(x):
    return x if isinstance(x, list) else [x] if x is not None else []


def text_of(node):
    """OPS JSON wraps text as {"$": "..."}; paragraphs can be a list."""
    if isinstance(node, dict):
        return node.get("$", "")
    return " ".join(text_of(n) for n in as_list(node))


def parse_family(data):
    """Return (abstract, lang, publication) for the best abstract in a family response."""
    members = as_list(data["ops:world-patent-data"]["ops:patent-family"]["ops:family-member"])
    candidates = []
    for member in members:
        for doc in as_list(member.get("exchange-document")):
            biblio = doc.get("bibliographic-data", {})
            pub_date = ""
            for docid in as_list(biblio.get("publication-reference", {}).get("document-id")):
                pub_date = text_of(docid.get("date")) or pub_date
            pub = f"{doc.get('@country', '')}{doc.get('@doc-number', '')}{doc.get('@kind', '')}"
            for abstract in as_list(doc.get("abstract")):
                text = re.sub(r"\s+", " ", text_of(abstract.get("p"))).strip()
                if text:
                    candidates.append((abstract.get("@lang", ""), pub_date, pub, text))
    if not candidates:
        return None

    def rank(c):
        lang = c[0]
        return (LANG_PREFERENCE.index(lang) if lang in LANG_PREFERENCE else len(LANG_PREFERENCE), c[1])

    lang, _, pub, text = min(candidates, key=rank)
    return text, lang, pub


def fetch_family(client, patent_id):
    m = re.fullmatch(r"([A-Z]{2})(\d+)([A-Z]\d?)?", patent_id)
    if not m:
        raise ValueError(f"unexpected publication number: {patent_id}")
    country, number, kind = m.groups()
    ref = epo_ops.models.Docdb(number, country, kind or "")
    for attempt in range(3):
        try:
            return client.family(reference_type="publication", input=ref, constituents=["biblio"]).json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def is_complete(path):
    """Cached responses must contain bibliographic data (older runs may lack it)."""
    return path.exists() and '"exchange-document"' in path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="ignore cached responses")
    args = parser.parse_args()

    key, secret = credentials()
    client = epo_ops.Client(key=key, secret=secret, accept_type="json")
    patents = pd.read_csv(PATENTS, dtype=str, keep_default_na=False)
    CACHE.mkdir(parents=True, exist_ok=True)

    n_requests, failed, rows = 0, [], []
    for row in patents.itertuples():
        cached = CACHE / f"family_{row.family_id}.json"
        if args.refresh or not is_complete(cached):
            try:
                data = fetch_family(client, row.patent_id)
            except (requests.RequestException, ValueError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", "")
                failed.append(f"{row.patent_id} {status or exc}")
                continue
            n_requests += 1
            cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        best = parse_family(json.loads(cached.read_text(encoding="utf-8")))
        if best:
            text, lang, pub = best
            rows.append({"family_id": row.family_id, "abstract": text, "lang": lang, "source_publication": pub})

    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    langs = pd.Series([r["lang"] for r in rows]).value_counts().to_dict()
    print(f"families:           {len(patents)}")
    print(f"requests made:      {n_requests} (others from cache)")
    print(f"with abstract:      {len(rows)}  languages: {langs}")
    print(f"without abstract:   {len(patents) - len(rows) - len(failed)}")
    print(f"failed:             {len(failed)}" + "".join(f"\n  {f}" for f in failed))
    print(f"saved:              {OUT}")


if __name__ == "__main__":
    main()
