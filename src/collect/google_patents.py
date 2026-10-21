"""Fill in text for patents that EPO OPS gives only a title for, from Google Patents.

Some older Italian patents and utility models have no abstract in any family member. Their
Google Patents pages sometimes carry an abstract, or at least the description (technical
field and summary). For each title-only patent in data/processed/patents.csv we try every
publication of the family, in Italian and English, one request every DELAY_S seconds.
robots.txt of patents.google.com allows /patent/ pages and is checked before fetching.

Text priority: abstract; otherwise the opening of the description (technical field, then
the first paragraphs), capped at MAX_CHARS. Italian text is machine-translated to English
(Helsinki-NLP/opus-mt-it-en, run locally) so that all patent texts are in one language.

Outputs (not committed, raw data):
    data/raw/google_patents/<publication>_<lang>.html   cached pages
    data/raw/google_patents_abstracts.json              [{"family_id", "abstract", "lang", "source_publication"}]
Merge with src/clean/merge_abstracts.py, after OPS and before the Espacenet page extracts.

Usage:
    python src/collect/google_patents.py [--refresh]
"""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

PATENTS = Path("data/processed/patents.csv")
CACHE = Path("data/raw/google_patents")
OUT = Path("data/raw/google_patents_abstracts.json")
BASE = "https://patents.google.com"
DELAY_S = 3.0
MAX_CHARS = 900
MT_MODEL = "Helsinki-NLP/opus-mt-it-en"
# Description headings and boilerplate that carry no technical content
SKIP = re.compile(r"^(descrizione|description|titolo|title|campo tecnico|technical field|background|"
                  r"stato della tecnica|sfondo|\[\d+\])\W*$", re.I)


def clean(text):
    text = re.sub(r"\[\d{4}\]", " ", text)          # paragraph numbers like [0005]
    text = text.replace("?", "'") if re.search(r"\w\?\w", text) else text  # broken apostrophes
    return re.sub(r"\s+", " ", text).strip()


def extract(html):
    """Return (text, kind) with kind 'abstract' or 'description', or (None, None)."""
    soup = BeautifulSoup(html, "html.parser")
    ab = soup.find("section", itemprop="abstract")
    if ab:
        text = clean(ab.get_text(" ", strip=True).removeprefix("Abstract"))
        if len(text) > 80:
            return text[:MAX_CHARS], "abstract"
    de = soup.find("section", itemprop="description")
    if de:
        paras = [clean(p.get_text(" ", strip=True)) for p in de.find_all(["p", "div"], recursive=True)
                 if not p.find(["p", "div"])]
        paras = [p for p in paras if len(p) > 40 and not SKIP.match(p) and not p.lower().startswith(("titolo", "title"))]
        text = " ".join(paras)
        if len(text) > 80:
            return text[:MAX_CHARS].rsplit(" ", 1)[0], "description"
    return None, None


def is_italian(text):
    it = len(re.findall(r"\b(il|la|di|che|per|della|delle|con|una|sono|nel|del|gli|le|un)\b", text, re.I))
    en = len(re.findall(r"\b(the|and|of|for|with|to|is|are|an|by|from|that)\b", text, re.I))
    return it > en


BOILERPLATE = re.compile(
    r"(description|descrizione) (of|dell)[’'\s]*(the )?(industrial )?invenzione? industriale.*?(entitled|titled|dal titolo)\s*:?"
    r"|description of the industrial invention.*?(entitled|titled|entity)\s*:?"
    r"|\b(campo dell[’']invenzione|field of (the )?invention|campo di applicazione|field of application|scope|description)\b\s*[.·:]?",
    re.I)


def english_part(text):
    """Google shows Italian originals next to its own English translation: keep the English
    sentences when there are enough of them, drop headings, repeated titles and duplicates.
    Returns (text, already_in_english_by_google)."""
    text = BOILERPLATE.sub(" ", text)
    sents = [s.strip(" \"“”'?·") for s in re.split(r"(?<=[.;:!?])\s+|\s+(?=[“\"])", text)]
    sents = [s for s in sents if len(s) > 25]
    english = [s for s in sents if not is_italian(s)]
    chosen = english if len(" ".join(english)) >= 150 else sents
    seen, out = set(), []
    for s in chosen:
        key = re.sub(r"\W+", "", s.lower())[:60]
        if key not in seen:
            seen.add(key)
            out.append(s if s.endswith((".", ";", ":")) else s + ".")
    return " ".join(out)[:MAX_CHARS], chosen is english


def translate(texts):
    from transformers import MarianMTModel, MarianTokenizer
    tok, model = MarianTokenizer.from_pretrained(MT_MODEL), MarianMTModel.from_pretrained(MT_MODEL)
    out = []
    for text in texts:
        sents = [s for s in re.split(r"(?<=[.;:])\s+", text) if s]
        batch = tok(sents, return_tensors="pt", padding=True, truncation=True)
        out.append(" ".join(tok.batch_decode(model.generate(**batch, num_beams=4, max_new_tokens=400),
                                             skip_special_tokens=True)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="ignore cached pages")
    args = parser.parse_args()

    ua = yaml.safe_load(open("config.yaml", encoding="utf-8"))["startups"]["websites"]["user_agent"]
    session = requests.Session()
    session.headers["User-Agent"] = ua
    robots = RobotFileParser()
    robots.parse(session.get(BASE + "/robots.txt", timeout=30).text.splitlines())

    patents = pd.read_csv(PATENTS, dtype=str, keep_default_na=False)
    todo = patents[patents["text_source"] == "title"]
    CACHE.mkdir(parents=True, exist_ok=True)

    found, n_requests = [], 0
    for r in todo.itertuples():
        pubs = [r.patent_id] + [p for p in r.all_publications.split("|") if p and p != r.patent_id]
        best = None
        for pub in pubs:
            for lang in ("en", "it"):
                url = f"{BASE}/patent/{pub}/{lang}"
                if not robots.can_fetch(ua, url):
                    continue
                cached = CACHE / f"{pub}_{lang}.html"
                if args.refresh or not cached.exists():
                    time.sleep(DELAY_S)
                    n_requests += 1
                    resp = session.get(url, timeout=30)
                    if resp.status_code != 200:
                        cached.write_text("", encoding="utf-8")
                        continue
                    cached.write_bytes(resp.content)
                html = cached.read_bytes()
                if not html:
                    continue
                text, kind = extract(html)
                # An abstract beats a description; the first description found is kept as fallback
                if text and (best is None or (kind == "abstract" and best[1] != "abstract")):
                    best = (text, kind, pub)
                if best and best[1] == "abstract":
                    break
            if best and best[1] == "abstract":
                break
        if best:
            found.append({"family_id": r.family_id, "text": best[0], "kind": best[1], "source_publication": best[2]})

    for f in found:
        f["text"], f["translated"] = english_part(f["text"])
    italian = [i for i, f in enumerate(found) if is_italian(f["text"])]
    if italian:
        for i, t in zip(italian, translate([found[i]["text"] for i in italian])):
            found[i]["text"], found[i]["translated"] = t, True
    rows = [{"family_id": f["family_id"], "abstract": f["text"], "lang": "en",
             "source_publication": f["source_publication"] + (" (description)" if f["kind"] == "description" else "")
             + (" (machine-translated)" if f.get("translated") else "")} for f in found]
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"title-only patents:   {len(todo)}")
    print(f"requests made:        {n_requests} (others from cache)")
    print(f"text found:           {len(found)}  "
          f"(abstract: {sum(f['kind'] == 'abstract' for f in found)}, description: {sum(f['kind'] == 'description' for f in found)}, "
          f"translated: {len(italian)})")
    print(f"still title only:     {len(todo) - len(found)}")
    print(f"saved:                {OUT}")


if __name__ == "__main__":
    main()
