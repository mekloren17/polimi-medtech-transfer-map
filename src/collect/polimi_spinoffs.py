"""Download the public list of Politecnico di Milano spin-offs (Technology Transfer Office).

Source: https://www.polimi.it/en/research/technology-transfer/spin-off
The page lists the active accredited spin-offs, each with a detail page giving legal name,
year of incorporation, field, activity, services, target market and website. Spin-offs no
longer active are not listed, so links to older companies are missed.

Only company-level fields are kept: the contact e-mail is dropped and no people are named
on these pages. robots.txt is checked and requests are spaced by DELAY_S seconds.

Outputs (not committed, raw data):
    data/raw/polimi_spinoffs/<slug>.html   cached pages
    data/raw/polimi_spinoffs.json          one record per spin-off

Usage:
    python src/collect/polimi_spinoffs.py [--refresh]
"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
import yaml
from bs4 import BeautifulSoup

BASE = "https://www.polimi.it"
LIST_URL = BASE + "/en/research/technology-transfer/spin-off"
CACHE = Path("data/raw/polimi_spinoffs")
OUT = Path("data/raw/polimi_spinoffs.json")
DELAY_S = 1.0
FIELDS = {
    "Year of incorporation": "founded_year",
    "Field": "field",
    "Activity": "activity",
    "Services": "services",
    "Target Market": "target_market",
    "Website": "website",
}


def get(session, url, path, refresh):
    if path.exists() and not refresh:
        return path.read_bytes()
    time.sleep(DELAY_S)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    return resp.content


def parse_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    lines = soup.get_text("\n", strip=True).split("\n")
    start = lines.index("You are here:")
    # Breadcrumb ends with "Spin-off", <short name>, then the "Spin-off" heading and legal name
    i = lines.index("Spin-off", start + 5)
    record = {"legal_name": lines[i + 1]}
    for k in range(i + 2, min(i + 40, len(lines) - 1)):
        if lines[k] == "Polimi Community":
            break
        if lines[k] in FIELDS:
            record[FIELDS[lines[k]]] = lines[k + 1]
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="ignore cached pages")
    args = parser.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["startups"]["websites"]
    session = requests.Session()
    session.headers["User-Agent"] = cfg["user_agent"]
    robots = RobotFileParser()
    robots.parse(session.get(BASE + "/robots.txt", timeout=30).text.splitlines())
    if not robots.can_fetch(cfg["user_agent"], LIST_URL):
        raise SystemExit("robots.txt disallows the spin-off pages")

    CACHE.mkdir(parents=True, exist_ok=True)
    listing = BeautifulSoup(get(session, LIST_URL, CACHE / "_list.html", args.refresh), "html.parser")
    slugs = {}
    for a in listing.find_all("a", href=True):
        href = a["href"].rstrip("/")
        if href.startswith("/en/research/technology-transfer/spin-off/"):
            name = a.get_text(strip=True)
            slug = href.rsplit("/", 1)[-1]
            if name and name != "Discover":
                slugs[slug] = name
            else:
                slugs.setdefault(slug, "")

    records, failed = [], []
    for slug, name in sorted(slugs.items()):
        url = urljoin(BASE, f"/en/research/technology-transfer/spin-off/{slug}")
        try:
            record = parse_detail(get(session, url, CACHE / f"{slug}.html", args.refresh))
        except (requests.RequestException, ValueError, IndexError) as exc:
            failed.append(f"{slug}: {type(exc).__name__}")
            continue
        records.append({"slug": slug, "name": name or record["legal_name"], "url": url} | record)

    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"spin-offs listed:   {len(slugs)}")
    print(f"parsed:             {len(records)}")
    print(f"with website:       {sum(bool(r.get('website')) for r in records)}")
    print(f"failed:             {len(failed)}" + "".join(f"\n  {f}" for f in failed))
    print(f"saved:              {OUT}")


if __name__ == "__main__":
    main()
