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

Model, threshold and scope are set in `config.yaml`. The threshold is calibrated on labelled patent–startup pairs (`data/manual/calibration_pairs.csv`, see `docs/labelling.md`); the model comparison is saved in `data/processed/calibration_report.json`.

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

## Related work

<!-- TO VERIFY before publishing: every reference below was compiled from abstracts and
     catalogue pages, not full texts. Check authors, year, pages and DOI on the publisher's
     site, and read at least introduction and conclusions before keeping a claim. Entries
     marked [check DOI] could not be confirmed at all. -->

Each part of this project has precedents; the combination does not seem to. Earlier work matches
university texts to company texts, or patents to startups, but from a single firm's point of
view (who should we partner with or acquire?). This map starts from a university's portfolio,
reads young companies from their own websites, compares Italian and English texts with a
multilingual model, and reports the **gaps** rather than recommendations.

- **University research against company websites.** Woltmann and Alkærsig compare university
  publications with companies' websites and documents through text mining to trace
  knowledge transfer [1].
- **Patents against startups.** Kim, Kim and Sohn match patent abstracts with Crunchbase
  startup profiles (doc2vec) to suggest startups to an acquiring firm [2]. Chung, Ko and Yoon
  use patents and language-model similarity to find university inventor groups for a firm [3].
- **Text similarity between patents.** Arts, Cassiman and Gomez show that text similarity
  between patents agrees with expert judgement [4], which motivates checking the threshold
  against labelled pairs here. Hain et al. measure patent similarity with text
  embeddings [5]; Ascione and Sterzi compare embedding models for this task [6].
- **Firm websites as data.** Kinne and Axenbeck build a web-mining framework for firm websites
  and show that website availability and content vary with firm size, age and sector [7]:
  startups without a usable website cannot appear on this map.

1. Woltmann, S. L., & Alkærsig, L. (2018). Tracing knowledge transfer from universities to industry: a text mining approach. *Scientometrics*, 117(1), 449–472. https://doi.org/10.1007/s11192-018-2849-9
2. Kim, J., Kim, J., & Sohn, S. Y. (2020). Recommendation of startups as technology cooperation candidates from the perspectives of similarity and potential: A deep learning approach. *Decision Support Systems*, 130, 113229. https://doi.org/10.1016/j.dss.2019.113229
3. Chung, J., Ko, N., & Yoon, J. (2021). Inventor group identification approach for selecting university-industry collaboration partners. *Technological Forecasting and Social Change*, 171. [check DOI]
4. Arts, S., Cassiman, B., & Gomez, J. C. (2018). Text matching to measure patent similarity. *Strategic Management Journal*, 39(1), 62–84. https://doi.org/10.1002/smj.2699
5. Hain, D. S., Jurowetzki, R., Buchmann, T., & Wolf, P. (2022). A text-embedding-based approach to measuring patent-to-patent technological similarity. *Technological Forecasting and Social Change*, 177, 121559. https://doi.org/10.1016/j.techfore.2022.121559 [check DOI]
6. Ascione, G. S., & Sterzi, V. (2024). A comparative analysis of embedding models for patent similarity. Preprint, arXiv:2403.16630.
7. Kinne, J., & Axenbeck, J. (2020). Web mining for innovation ecosystem mapping: a framework and a large-scale pilot study. *Scientometrics*, 125. https://doi.org/10.1007/s11192-020-03726-9

## Limitations

- Semantic similarity is a signal, not proof of a real fit: at the chosen threshold, about four in ten links in the calibration set are not relevant (precision 0.57). Results are a starting point for human review.
- Licences and research contracts are mostly not public, so a technology marked "orphan" might be licensed privately, and a startup marked "research-less" may well work with Polimi.
- The register covers innovative startups for at most five years; established companies are outside the map, and startups without a usable website description could not be compared.
- Personal data: inventors and founders are not profiled; only organisation-level data is published.

Corrections are welcome: open an issue if a company or patent is described wrongly.

## License

Code: [MIT](LICENSE). Data: subject to the terms of the original sources (EPO, InfoCamere, Politecnico di Milano, company websites); the processed tables are shared for research and review.
