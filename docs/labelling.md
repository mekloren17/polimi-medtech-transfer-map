# Reviewing the calibration labels

The similarity threshold (`similarity.threshold` in `config.yaml`) and the precision and recall
quoted on the site come from `data/manual/calibration_pairs.csv`. Each row is a patent–startup
pair with a `label`:

- `1` — **relevant**: the patent's technology is in the same specific field as the startup's
  product (same clinical problem or same device type); a licensing or research conversation
  would make sense.
- `0` — **not relevant**, including "both are medical but unrelated" (e.g. a prosthesis patent
  and a dental clinic).
- empty — **cannot be judged** from the texts (too vague); such rows are ignored.

The first version of the labels is a draft. Review every row before quoting the numbers.

## How to review

1. Open `data/manual/calibration_pairs.csv` in a spreadsheet. Sort it by `patent_id` so that
   pairs sharing a patent sit together: it is faster and keeps your judgement consistent.
2. Do **not** look up the similarity scores while labelling (the file has none on purpose):
   labels must not be influenced by what the model thinks.
3. For each row read `patent_text` and `startup_text`, then ask one question:
   *would the Polimi Technology Transfer Office have a concrete reason to call this company
   about this patent?* Yes → `1`, no → `0`, cannot tell → leave empty.
4. Write a short reason in `note` for every label you change and for borderline cases
   (e.g. "same device type: upper-limb exoskeleton", "both digital health, different problem").
5. Save as CSV (UTF-8, comma-separated), keeping the column names.

## How to check the labels are right

- **Consistency:** pairs with the same patent should not contradict each other without a
  reason in `note`. Filter by `patent_id` and read the `1`s together.
- **Second reader:** ask someone else to label 30 random rows blind, then compare. Agreement on
  25 or more (≥ 80%) is good; discuss the disagreements and fix the rule, not just the rows.
- **Re-label a sample later:** after a few days, label 20 rows again without looking. If you
  disagree with yourself often, the rule above needs to be sharper.
- **Coverage:** keep at least ~15–20 positives; with fewer, precision and recall swing a lot
  for a single row.

## After the review

```bash
python src/score/calibrate.py report sentence-transformers/paraphrase-multilingual-mpnet-base-v2 BAAI/bge-m3
```

Read the best-F1 threshold. If it differs from `similarity.threshold`, update `config.yaml`, then:

```bash
python src/score/similarity.py
python src/score/gaps.py
python src/build/site.py
```

The site picks up the new precision, recall and model comparison automatically.
To add pairs from the national data: rename the current file (keep it, it holds your labels),
run `python src/score/calibrate.py export ...` to create a new set, then copy your existing
labels into it by matching `patent_id` and `vat_number`. The export refuses to overwrite an
existing file, so labels are never lost by accident.

## Current state of the labels

The labels in the file were drafted by Claude (an LLM) against the rule above, reading only the
two texts, blind to the scores. Each row has a one-line reason in `note` and a `confidence`
(`high`, `medium`, `low`). To check them quickly: read every `1`, every `low` row, then a sample
of the `high` ones; change the label and the note where you disagree, and replace
"Claude, to check:" with your own note. Until that is done the site says the labels were drafted
with an LLM.
