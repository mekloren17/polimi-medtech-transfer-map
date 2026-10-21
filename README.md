# Polimi MedTech Transfer Map

**Which medical technologies developed at Politecnico di Milano are not (yet) becoming companies — and which Italian startups work close to them?**

This project maps the technology-transfer pipeline between Politecnico di Milano patents and the Italian medtech startup ecosystem, using only open data. Its main output is not the existing connections but the **gaps**:

- **Orphan technologies** — Polimi medtech patents with no spin-off, no company co-applicant link and no thematically close startup.
- **Research-less startups** — Italian medtech startups close to a Polimi patent but with no visible tie to Polimi.

Every link comes with a similarity score and the terms that explain it. Links are **candidates for human review**, not findings about any company.

> Independent research project. It is **not affiliated with, endorsed by or produced for Politecnico di Milano** or its Technology Transfer Office. "Polimi" only names the subject of the analysis.

## Outputs

1. **Interactive site** (`site/index.html`, for GitHub Pages): a navigable graph of patents, spin-offs and startups, the two gap lists and a method page.
2. **Processed datasets** in `data/processed/` (CSV), described in `docs/schema.md`.

## Data sources (all public)

| Entity | Source | Notes |
|---|---|---|
| Patents | Espacenet export + EPO Open Patent Services (OPS) | Polimi applications in the medtech IPC classes; abstracts from OPS (free account needed) |
| Patent texts, fallback | Google Patents | Only for patents with no abstract in OPS; `/patent/` pages allowed by robots.txt |
| Startups | InfoCamere register of innovative startups (startup.registroimprese.it) | Weekly open-data list, whole of Italy |
| Startup descriptions | Each startup's own homepage | Homepage only, robots.txt respected; e-mails, phones and personal names removed |
| Spin-offs | Polimi Technology Transfer Office public spin-off list | Active accredited spin-offs only |

How to obtain the raw files is explained in `data/raw/README.md`. Raw downloads are not committed.

## MedTech scope

- **Patents:** IPC subclasses A61B (diagnosis/surgery), A61F (prostheses, implants), A61L (medical materials), A61M (devices for introducing media), A61N (electro/radiation therapy), G16H (healthcare informatics).
- **Startups:** ATECO 32.50 and 26.60, plus a keyword filter on name and description (many medtech startups are registered under software or R&D codes). Keywords and candidate ATECO divisions are in `config.yaml`.

## Method

1. **Collect** raw data from each source (`src/collect/`).
2. **Clean & filter** to the medtech scope, match spin-offs and patent applicants to the startup register, machine-translate Italian texts for display (`src/clean/`).
3. **Embed** patent and startup texts with a multilingual sentence-embedding model (`src/embed/`).
4. **Score** cosine similarity between every patent and every startup; keep pairs above the threshold (at most N per patent) with the terms that explain them (`src/score/similarity.py`).
5. **Classify gaps** (`src/score/gaps.py`):
   - a patent is *orphan* if no startup reaches the threshold and no known tie exists;
   - a startup is *research-less* if a Polimi patent reaches the threshold but no known tie exists.
6. **Build** the site (`src/build/site.py`).

Model, threshold and scope are set in `config.yaml`. The threshold is calibrated on hand-labelled patent–startup pairs (`data/manual/calibration_pairs.csv`, see `docs/labelling.md`); the model comparison is saved in `data/processed/calibration_report.json`.

## Reproduce it

Tested with Python 3.12.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

With the processed data already in the repository, rebuilding the results only needs:

```bash
python src/embed/embed.py
python src/score/similarity.py
python src/score/gaps.py
python src/build/site.py
```

To start from the raw data, first follow `data/raw/README.md`, then run in order:

```bash
python src/collect/startups.py
python src/collect/websites.py
python src/clean/startups.py
python src/collect/epo_ops.py
python src/collect/google_patents.py
python src/clean/merge_abstracts.py data/processed/patents.csv data/raw/ops_abstracts.json=epo_ops data/raw/google_patents_abstracts.json=google_patents data/raw/abstracts.json=espacenet_page
python src/collect/polimi_spinoffs.py
python src/clean/spinoffs.py
python src/clean/edges_known.py
python src/clean/translate_en.py
```

and then the four commands above. The initial `patents.csv` table was built from the Espacenet export (`data/raw/espacenet_export.csv`); that conversion is not yet a script.

## Repository structure

```
├── config.yaml            # scope, keywords, model, threshold
├── data/
│   ├── raw/               # untouched downloads (not committed; README explains how to get them)
│   ├── manual/            # hand-edited inputs: calibration labels, redacted descriptions
│   └── processed/         # clean tables, edges, gap lists, calibration report
├── docs/
│   ├── schema.md          # data model
│   └── labelling.md       # how to label and check the calibration pairs
├── src/
│   ├── collect/           # one script per source
│   ├── clean/
│   ├── embed/
│   ├── score/
│   └── build/             # site generation (template.html + site.py)
└── site/                  # generated site for GitHub Pages
```

## Roadmap

- [x] v0.1 — Polimi medtech patents + Lombard startups, similarity scoring, orphan list
- [x] v0.1.1 — startups extended to the whole of Italy, grouped by macro-area
- [x] v0.2 — spin-offs and known ties; static site with graph and method page; calibrated threshold
- [ ] v0.3 — CORDIS EU research projects as a second kind of technology
- [ ] v1.0 — other universities and IRCCS; other verticals

## Limitations

- Semantic similarity is a signal, not proof of a real fit: at the chosen threshold, roughly half of the links in the calibration set are not relevant. Results are a starting point for human review.
- Licences and research contracts are mostly not public, so a technology marked "orphan" might be licensed privately, and a startup marked "research-less" may well work with Polimi.
- The register covers innovative startups for at most five years; established companies are outside the map, and startups without a usable website description could not be compared.
- Personal data: inventors and founders are not profiled; only organisation-level data is published.

Corrections are welcome: open an issue if a company or patent is described wrongly.

## License

Code: [MIT](LICENSE). Data: subject to the terms of the original sources (EPO, InfoCamere, Politecnico di Milano, company websites); the processed tables are shared for research and review.
