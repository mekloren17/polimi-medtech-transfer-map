# Data schema

All processed tables are CSV files in `data/processed/` (UTF-8, comma-separated). List fields
are joined with `|`. Embeddings are Parquet files in `data/processed/embeddings/<model>/`
(not committed, rebuilt by `src/embed/embed.py`).

Only organisations are published: inventors and founders are counted, never named.

## Entities

### `patents.csv` — Polimi medtech patent families (one row per family)

| Field | Description |
|---|---|
| patent_id | Representative publication number (e.g. `EP2526859A1`) |
| all_publications | All publications of the family in the Espacenet export |
| family_id | DOCDB family id, the deduplication key |
| title | Title as published |
| applicants | Organisation applicants (individuals removed) |
| co_applicants | Applicants other than Politecnico di Milano |
| n_individual_applicants | Number of applicants who are people (count only) |
| ipc_codes / ipc_subclasses | Full IPC codes and their 4-character subclasses |
| medtech_subclasses | Subclasses in the medtech scope of `config.yaml` |
| priority_date / first_publication | Earliest priority and first publication dates |
| n_inventors | Number of inventors (count only) |
| source | Where the row comes from (`espacenet_export`) |
| text_for_embedding | Text used for the similarity: abstract, or title if none |
| text_source | `abstract` or `title` |
| abstract / abstract_lang | Abstract and its language |
| abstract_source | `epo_ops`, `google_patents` or `espacenet_page` |
| abstract_publication | Publication the abstract was taken from |

### `startups.csv` — Italian medtech innovative startups

| Field | Description |
|---|---|
| vat_number | Codice fiscale / VAT number, the key |
| name | Legal name in the register |
| municipality / province / region / macro_area | Location; `macro_area` is the ISTAT area (North-West, North-East, Centre, South, Islands) |
| ateco / ateco_division | ATECO 2007 code and its division label |
| founded / registered_startup | Incorporation date and date of entry in the startup register |
| description | Short description from the company homepage (personal data removed) |
| description_source | `website_meta`, `website_text`, or `*_redacted` when personal data was removed by hand; empty if no description |
| is_polimi_spinoff | True if the company is an accredited Polimi spin-off |
| website | Website declared in the register |
| owns_patents | Register flag (`SI` / `NO`) |
| match_reason | Why it is in scope: `ateco`, `keyword` or `ateco+keyword` |
| matched_keywords | Medtech keywords found in name and description |
| list_date | Date of the register list used |

### `spinoffs.csv` — accredited Polimi spin-offs (TTO public list)

| Field | Description |
|---|---|
| spinoff_id | Slug of the TTO page |
| name / founded / field / description / website | As published by the TTO |
| vat_number | Found in the startup register; empty for spin-offs older than its 5-year window |
| vat_match | How the VAT number was found: `website`, `name`, or empty |
| department | Not published by the TTO, left empty |
| is_medtech / medtech_keywords | Same keyword rule as the startups |
| evidence | URL of the TTO page |

## Relations

### `edges_known.csv` — ties visible in public records

| Field | Description |
|---|---|
| source_id / source_type | `spinoff` or `patent` |
| target_id / target_type | `startup` or `spinoff` |
| relation | `same_company` (spin-off is a registered startup) or `co_applicant` (company co-filed the patent) |
| evidence | Source URL or record |

### `edges_similarity.csv` — patent–startup pairs at or above the threshold

| Field | Description |
|---|---|
| tech_id / tech_type | Patent id, `patent` |
| startup_id | VAT number |
| score | Cosine similarity of the two embeddings |
| top_terms | Words and phrases close to both texts, as an explanation |
| tech_text_source | `abstract` or `title` |
| low_confidence | True when the patent is known only by its title |
| model / run_date | Embedding model and date of the run |

## Derived views

### `orphan_technologies.csv`

Patents with no known tie and no startup at or above the threshold, sorted by `best_score`.
Adds `best_startup_id` / `best_startup_name` (closest startup, below the threshold),
`industry_co_applicants` (companies that co-filed the patent: an industrial route exists),
`threshold` and `model`.

### `researchless_startups.csv`

Startups with at least one patent at or above the threshold and no known tie to Polimi.
`n_matches` and `n_matches_high_confidence` count the patents linked; `best_patent_id`,
`best_patent_title`, `best_score` and `top_terms` describe the closest one.

### `translations_en.csv`

English machine translations of Italian texts shown on the site (`kind`, `key`, `source`,
`text_en`, `model`). Scores are always computed on the original texts.

### `calibration_report.json`

Model comparison on the labelled pairs in `data/manual/calibration_pairs.csv`: AUC, best
threshold and F1 per model.
