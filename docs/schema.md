# Data schema

All processed tables live in `data/processed/` as CSV (or Parquet for embeddings).

## Entities

### `patents`
| Field | Type | Description |
|---|---|---|
| patent_id | str | EPO publication number (family-level key: `family_id`) |
| family_id | str | DOCDB family, used to deduplicate |
| title | str | |
| abstract | str | Used for embeddings |
| applicants | list[str] | Organisations only |
| ipc_codes | list[str] | |
| priority_date | date | |
| status | str | granted / pending / lapsed (if available) |
| n_inventors | int | Count only, no names |

### `eu_projects`
| Field | Type | Description |
|---|---|---|
| project_id | str | CORDIS id |
| acronym | str | |
| title | str | |
| objective | str | Used for embeddings |
| programme | str | e.g. Horizon Europe cluster |
| start_date / end_date | date | |
| polimi_role | str | coordinator / participant |
| polimi_contribution_eur | float | |
| department | str | If derivable |

### `spinoffs`
| Field | Type | Description |
|---|---|---|
| spinoff_id | str | Slug of the Polimi TTO page |
| name | str | Legal name |
| vat_number | str | Join key with `startups`; empty if not in the innovative-startup registry |
| vat_match | str | `website` or `name`: how the VAT number was found |
| founded | int | Year of incorporation |
| department | str | Originating department (not published by the TTO: empty for now) |
| field | str | Field as stated by the TTO |
| description | str | Activity, services and target market |
| is_medtech | bool | Medtech keywords (config.yaml) found in the TTO text |
| medtech_keywords | list[str] | |
| website | str | |
| evidence | str | TTO page URL |

Only spin-offs still active and listed by the TTO are included (91 of 142 accredited).

### `startups`
| Field | Type | Description |
|---|---|---|
| vat_number | str | Primary key |
| name | str | |
| municipality | str | |
| region | str | As in the register; scope set by `startups.regions` |
| macro_area | str | ISTAT macro-area: North-West, North-East, Centre, South, Islands |
| ateco | str | |
| founded | date | |
| description | str | Used for embeddings |
| is_polimi_spinoff | bool | From join with `spinoffs` |

## Relations

### `edges_known`
Verified relations from sources.
| Field | Type | Description |
|---|---|---|
| source_id | str | |
| source_type | str | patent / eu_project / spinoff / startup |
| target_id | str | |
| target_type | str | |
| relation | str | `same_company` (spin-off is the startup), `co_applicant` (company applies for a Polimi patent); later e.g. `participates_in` |
| evidence | str | Source URL or reference |

### `edges_similarity`
Computed relations.
| Field | Type | Description |
|---|---|---|
| tech_id | str | patent_id or project_id |
| tech_type | str | patent / eu_project |
| startup_id | str | vat_number |
| score | float | Cosine similarity |
| top_terms | list[str] | Terms explaining the match |
| tech_text_source | str | `abstract` or `title`: text the technology was embedded from |
| low_confidence | bool | True when only the title was available (short, often Italian: less reliable score) |
| model | str | Embedding model name |
| run_date | date | |

## Derived views

Built by `src/score/gaps.py`.

- **`orphan_technologies`**: technologies with no `edges_known` to a spin-off/startup and max `score` < threshold.
  Adds `best_score` / `best_startup_id` (closest startup even below threshold), `low_confidence`
  (title only) and `industry_co_applicants` (company co-applicants: such a technology already
  has an industrial partner and is orphan only with respect to startups).
- **`researchless_startups`**: startups with at least one `score` ≥ threshold and no `edges_known` to Polimi
  (not a spin-off, not a co-applicant). Adds match counts, best patent and `only_low_confidence`
  (every match comes from a title-only patent).
