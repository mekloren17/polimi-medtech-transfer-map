"""Download the weekly open-data list of Italian innovative startups (InfoCamere).

Source: https://startup.registroimprese.it -> "Elenchi e statistiche startup" -> "Elenco settimanale".
The zip contains `startup.xls` and `startup_DDMMYYYY.csv` (pipe-separated, latin-1); we keep
both untouched in data/raw/startups/.

The portal sits behind a bot-protection layer that usually answers scripted requests with a
JavaScript challenge page instead of the file. We do not try to get around it: if the download
is blocked, fetch the zip in a browser and register it with --zip.

Usage:
    python src/collect/startups.py                 # try the direct download
    python src/collect/startups.py --zip PATH      # use a zip downloaded by hand
"""
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

import requests

URL = "https://startup.registroimprese.it/isin/report?fileId=startup.zip"
OUT_DIR = Path("data/raw/startups")
OUT_ZIP = OUT_DIR / "startup.zip"


def download(dest):
    resp = requests.get(URL, timeout=60, headers={"User-Agent": "polimi-medtech-transfer-map"})
    resp.raise_for_status()
    if not resp.content.startswith(b"PK"):
        return False
    dest.write_bytes(resp.content)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", type=Path, help="zip downloaded by hand from the portal")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.zip:
        if args.zip.resolve() != OUT_ZIP.resolve():
            shutil.copyfile(args.zip, OUT_ZIP)
        source = f"manual ({args.zip})"
    elif download(OUT_ZIP):
        source = URL
    else:
        sys.exit(
            "Download blocked by the portal's bot protection (got an HTML page, not a zip).\n"
            f"Open {URL} in a browser, save the zip, then run:\n"
            "    python src/collect/startups.py --zip PATH/TO/startup.zip"
        )

    with zipfile.ZipFile(OUT_ZIP) as zf:
        names = zf.namelist()
        csvs = [n for n in names if re.fullmatch(r"startup_\d{8}\.csv", n)]
        if not csvs:
            sys.exit(f"Unexpected zip content: {names}")
        zf.extract(csvs[0], OUT_DIR)
    date = re.search(r"\d{8}", csvs[0]).group()
    n_rows = sum(1 for _ in open(OUT_DIR / csvs[0], encoding="latin-1")) - 1

    print(f"source:      {source}")
    print(f"zip content: {names}")
    print(f"list date:   {date[:2]}/{date[2:4]}/{date[4:]}")
    print(f"startups:    {n_rows} (Italy)")
    print(f"saved:       {OUT_DIR / csvs[0]}")


if __name__ == "__main__":
    main()
