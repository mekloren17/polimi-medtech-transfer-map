# Raw data

Files in this folder are not committed: they are untouched downloads, may contain
personal data (e.g. inventor names) and are subject to the licences of their sources.
Recreate them as follows.

## Patents

| File | How to obtain |
|---|---|
| `espacenet_export.csv` | Espacenet advanced search, query `(pa = "politecnico di milano" OR pa = "milano politecnico") AND ipc any "A61B A61F A61L A61M A61N G16H"`, export results as CSV (117 results at the time of writing). |
| `ops/family_<id>.json`, `ops_abstracts.json` | Run `python src/collect/epo_ops.py` (EPO Open Patent Services). Needs a free OPS account: put the app's Consumer Key and Secret in a `.env` file in the project root as `OPS_KEY=...` and `OPS_SECRET=...`. This is the main abstract source. |
| `abstracts.json` | Fallback: list of `{"family_id", "abstract", "lang"}` extracted manually from the Espacenet results page (first version of the dataset). |

Merge both into the patents table, OPS first:
`python src/clean/merge_abstracts.py data/processed/patents.csv data/raw/ops_abstracts.json=epo_ops data/raw/abstracts.json=espacenet_page`

Espacenet must not be scraped (anti-bot protection and terms of use).

## Startups

| File | How to obtain |
|---|---|
| `startups/startup_<date>.xlsx` (and the zip it came in) | Weekly list of innovative startups published by InfoCamere at <https://startup.registroimprese.it> → *Elenchi e statistiche startup* → *Elenco settimanale* (`https://startup.registroimprese.it/isin/report?fileId=startup.zip`). Run `python src/collect/startups.py`; if the download is blocked, download the zip in a browser and pass it with `--zip PATH`. |
