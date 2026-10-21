"""Collect a short description of each candidate Italian startup from its own homepage.

The open-data startup list has no business description, only a website. For every
startup in scope (config.yaml regions) in a candidate ATECO division (config.yaml) we fetch the homepage only,
after checking robots.txt for our user agent, and keep:
title, meta description, og:description, page language and the first paragraphs of text.

Output: data/raw/startups/websites.jsonl, one record per startup (not committed).
Already-fetched startups are skipped, so an interrupted run can be resumed; use --refresh
to start from scratch.

Usage:
    python src/collect/websites.py [--refresh] [--limit N]
"""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw/startups")
OUT = RAW_DIR / "websites.jsonl"
MAX_BYTES = 3_000_000


def load_candidates(cfg):
    csvs = sorted(RAW_DIR.glob("startup_*.csv"), key=lambda p: pd.to_datetime(p.stem[-8:], format="%d%m%Y"))
    if not csvs:
        raise SystemExit("No startup_*.csv in data/raw/startups/: run src/collect/startups.py first.")
    df = pd.read_csv(csvs[-1], sep="|", encoding="latin-1", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda s: s.str.strip())
    regions = [r.casefold() for r in cfg.get("regions") or []]  # empty: whole of Italy
    if regions:
        df = df[df["regione"].str.casefold().isin(regions)]
    ateco = df["ateco 2007"]
    is_candidate = ateco.str[:2].isin(cfg["candidate_ateco_divisions"]) | (
        (ateco.str[:2] + "." + ateco.str[2:4]).isin(cfg["ateco_codes"])
    )
    df = df[is_candidate]
    return df.rename(columns={"codice fiscale": "vat_number", "sito internet": "website"})[
        ["vat_number", "website"]
    ]


def normalise_url(url):
    url = url.strip().split()[0] if url.strip() else ""
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def robots_allows(session, url, user_agent, timeout):
    """True/False from robots.txt; a missing robots.txt (4xx) allows everything."""
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    resp = session.get(robots_url, timeout=timeout)
    if 400 <= resp.status_code < 500:
        return True
    if resp.status_code >= 500:
        return False  # server error: treat as disallowed, as major crawlers do
    parser = RobotFileParser()
    parser.parse(resp.text.splitlines())
    return parser.can_fetch(user_agent, url)


def extract(html, max_chars):
    soup = BeautifulSoup(html, "html.parser")

    def meta(**attrs):
        tag = soup.find("meta", attrs=attrs)
        return (tag.get("content") or "").strip() if tag else ""

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form"]):
        tag.decompose()
    paragraphs = []
    for p in soup.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(t) >= 40 and "cookie" not in t.lower():
            paragraphs.append(t)
        if sum(map(len, paragraphs)) >= max_chars:
            break
    html_tag = soup.find("html")
    return {
        "title": title[:300],
        "meta_description": meta(name=re.compile("^description$", re.I))[:1000],
        "og_description": meta(property="og:description")[:1000],
        "lang": (html_tag.get("lang") or "").strip()[:10] if html_tag else "",
        "text": " ".join(paragraphs)[:max_chars],
    }


def fetch(vat_number, website, web_cfg):
    rec = {"vat_number": vat_number, "website": website, "fetched_at": datetime.now(timezone.utc).isoformat()}
    url = normalise_url(website)
    if not url:
        return rec | {"status": "no_website"}
    session = requests.Session()
    session.headers["User-Agent"] = web_cfg["user_agent"]
    timeout = web_cfg["timeout_s"]
    candidates = [url] if url.startswith("http://") else [url, "http://" + url[len("https://"):]]
    last_error = ""
    for attempt in candidates:
        try:
            if not robots_allows(session, attempt, web_cfg["user_agent"], timeout):
                return rec | {"url": attempt, "status": "robots_disallowed"}
            resp = session.get(attempt, timeout=timeout, stream=True)
            body = resp.raw.read(MAX_BYTES, decode_content=True)
            ctype = resp.headers.get("Content-Type", "")
            rec |= {"url": attempt, "final_url": resp.url, "http_status": resp.status_code}
            if resp.status_code >= 400:
                return rec | {"status": "http_error"}
            if "html" not in ctype.lower():
                return rec | {"status": "not_html"}
            # Pass bytes: BeautifulSoup detects the charset from the page itself
            return rec | {"status": "ok"} | extract(body, web_cfg["max_text_chars"])
        except requests.RequestException as exc:
            last_error = type(exc).__name__
    return rec | {"url": url, "status": "unreachable", "error": last_error}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="discard previous results")
    parser.add_argument("--limit", type=int, help="fetch at most N startups (for testing)")
    args = parser.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["startups"]
    candidates = load_candidates(cfg)
    done = {}
    if OUT.exists() and not args.refresh:
        for line in open(OUT, encoding="utf-8"):
            r = json.loads(line)
            done[r["vat_number"]] = r
    todo = candidates[~candidates["vat_number"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)

    mode = "w" if args.refresh else "a"
    with open(OUT, mode, encoding="utf-8") as f, ThreadPoolExecutor(cfg["websites"]["workers"]) as pool:
        futures = [pool.submit(fetch, r.vat_number, r.website, cfg["websites"]) for r in todo.itertuples()]
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            done[rec["vat_number"]] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(futures)}")

    results = pd.DataFrame([done[v] for v in candidates["vat_number"] if v in done])
    has_desc = (results.get("meta_description", "").fillna("") != "") | (results.get("og_description", "").fillna("") != "")
    has_text = results.get("text", pd.Series("", index=results.index)).fillna("") != ""
    print(f"candidate startups:     {len(candidates)}")
    print(f"fetched this run:       {len(todo)}")
    print(f"status:                 {results['status'].value_counts().to_dict()}")
    print(f"with meta/og descr.:    {has_desc.sum()}")
    print(f"with paragraph text:    {has_text.sum()}")
    print(f"with any text:          {(has_desc | has_text).sum()}")
    print(f"saved:                  {OUT}")


if __name__ == "__main__":
    main()
