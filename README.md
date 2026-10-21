# Polimi MedTech Transfer Map

**Which medical technologies developed at Politecnico di Milano are not (yet) becoming companies — and which Italian startups could use them?**

This project maps the technology-transfer pipeline between Politecnico di Milano research and the Italian medtech startup ecosystem, using only open data. Its main output is not the existing connections but the **gaps**:

- **Orphan technologies** — Polimi medtech patents and research lines with no spin-off and no thematically close startup.
- **Research-less startups** — Italian medtech startups with a closely related Polimi research group or patent they are not (visibly) connected to.

Every link comes with a similarity score and the terms that justify it, so the analysis is transparent and reproducible.

## Outputs

1. **Interactive site** (GitHub Pages): navigable graph + ranked list of orphan technologies.
2. **Obsidian vault** (generated): one note per entity, links as relations — for exploration.
3. **Versioned datasets** in `data/processed/`.

## Data sources (all open)

| Entity | Source | Notes |
|---|---|---|
| Patents | EPO Open Patent Services (OPS) API | Free with registration; filter by applicant = Politecnico di Milano |
| EU research projects | CORDIS open data | Polimi participations, objectives, budgets |
| Publications (optional) | OpenAIRE | To enrich research-group topics |
| Spin-offs | Polimi Technology Transfer Office public lists | Manually curated where needed |
| Startups | Registro delle startup innovative (startup.registroimprese.it) | Whole of Italy; `startups.regions` in `config.yaml` narrows it (e.g. Lombardy) |

## MedTech scope

- **Patents:** IPC classes A61B (diagnosis/surgery), A61F (prostheses, implants), A61L (medical materials), A61M (devices for introducing media), A61N (electro/radiation therapy), G16H (healthcare informatics).
- **Startups:** ATECO 32.50 and 26.60, plus a keyword filter on descriptions (many medtech startups are registered under software/R&D codes).
- **EU projects:** health-related programmes and keyword filter on objectives.

## Method

1. **Collect** raw data from each source (`src/collect/`).
2. **Clean & filter** to the medtech scope (`src/clean/`).
3. **Embed** all texts (patent abstracts, project objectives, startup descriptions) with a multilingual sentence-embedding model (descriptions are often in Italian).
4. **Score** similarity between every technology and every startup; keep the top terms explaining each match.
5. **Classify gaps**:
   - a patent is *orphan* if no startup exceeds the similarity threshold and no spin-off is linked to it;
   - a startup is *research-less* if it has a Polimi technology above threshold but no known connection.
6. **Publish** the graph and gap lists to the site and the vault (`src/build/`).

Thresholds and model are set in `config.yaml` and documented in every output.

## Repository structure

```
├── config.yaml            # scope, thresholds, model
├── data/
│   ├── raw/               # untouched downloads (not all committed)
│   └── processed/         # clean tables + similarity edges
├── docs/
│   └── schema.md          # data model
├── src/
│   ├── collect/           # one script per source
│   ├── clean/
│   ├── embed/
│   ├── score/
│   └── build/             # site + Obsidian vault generation
├── site/                  # GitHub Pages output
└── vault/                 # generated Obsidian vault
```

## Roadmap

- [x] v0.1 — Polimi medtech patents + Lombard startups, similarity scoring, orphan list (CSV)
- [ ] v0.1.1 — startups extended to the whole of Italy, grouped by macro-area
- [ ] v0.2 — CORDIS projects and spin-offs added; static site with graph
- [ ] v0.3 — Obsidian vault generation; methodology page
- [ ] v1.0 — other universities and IRCCS; other verticals

## Limitations

- Semantic similarity is a signal, not proof of a real fit; results are a starting point for human review.
- Licensing agreements are mostly not public, so a technology marked "orphan" might be licensed privately.
- Personal data: inventors and founders are not profiled; only organisation-level data is published.

## License

Code: MIT. Data: subject to the licences of the original sources.
