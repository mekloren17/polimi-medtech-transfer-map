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
| spinoff_id | str | Internal id |
| name | str | |
| vat_number | str | Join key with `startups` |
| founded | date | |
| department | str | Originating department |
| description | str | |

### `startups`
| Field | Type | Description |
|---|---|---|
| vat_number | str | Primary key |
| name | str | |
| municipality | str | Lombardy only |
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
| relation | str | e.g. `originated_from`, `same_department`, `participates_in` |
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
| model | str | Embedding model name |
| run_date | date | |

## Derived views

- **`orphan_technologies`**: technologies with no `edges_known` to a spin-off/startup and max `score` < threshold.
- **`researchless_startups`**: startups with at least one `score` ≥ threshold and no `edges_known` to Polimi.
