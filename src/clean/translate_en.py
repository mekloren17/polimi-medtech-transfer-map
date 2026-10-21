"""Machine-translate the Italian texts shown on the site into English.

Texts: startup descriptions and patent titles (sector labels use the official English NACE
names instead, see src/build/site.py).
A text is translated sentence by sentence: sentences that look Italian (more Italian than
English function words) are translated, English ones are kept, so bilingual texts work too.
Model: Helsinki-NLP/opus-mt-it-en (MarianMT), run locally; texts are not sent anywhere.

Output: data/processed/translations_en.csv (kind, key, source, text_en, model). Rows whose
source text is unchanged are reused, so a rerun only translates new or edited texts.
Similarity scores are computed on the original texts; translations are for display and for
the explanatory top terms.

Usage:
    python src/clean/translate_en.py
"""
import re
from pathlib import Path

import pandas as pd
from transformers import MarianMTModel, MarianTokenizer

PROCESSED = Path("data/processed")
OUT = PROCESSED / "translations_en.csv"
MODEL = "Helsinki-NLP/opus-mt-it-en"
COLUMNS = ["kind", "key", "source", "text_en", "model"]

IT_WORDS = re.compile(r"\b(il|lo|la|di|che|per|della|delle|dei|degli|con|una|uno|sono|nel|nella|alla|"
                      r"del|gli|le|dispositivo|sistema|metodo|e|ed|da|tra|nostro|nostra|siamo)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|of|for|with|to|is|are|our|we|an|on|by|from|that|this)\b", re.I)


def is_italian(text):
    return len(IT_WORDS.findall(text)) > len(EN_WORDS.findall(text))


def sentences(text):
    """One piece per sentence: the language is decided per sentence, and pieces stay well
    inside the model's 512-token limit (descriptions are capped at about 600 characters)."""
    return [p for p in re.split(r"(?<=[.!?;])\s+|\s+(?=[“\"][A-Z])", text.strip()) if p]


def collect():
    startups = pd.read_csv(PROCESSED / "startups.csv", dtype=str, keep_default_na=False)
    patents = pd.read_csv(PROCESSED / "patents.csv", dtype=str, keep_default_na=False)
    rows = []
    for r in startups.itertuples():
        if r.description and any(is_italian(x) for x in sentences(r.description)):
            rows.append(("startup_description", r.vat_number, r.description))
    for r in patents.itertuples():
        title = r.title.capitalize() if r.title.isupper() else r.title
        if is_italian(title):
            rows.append(("patent_title", r.patent_id, title))
    return pd.DataFrame(rows, columns=["kind", "key", "source"])


def main():
    todo = collect()
    done = pd.read_csv(OUT, dtype=str, keep_default_na=False) if OUT.exists() else pd.DataFrame(columns=COLUMNS)
    merged = todo.merge(done[["kind", "key", "source", "text_en"]], on=["kind", "key", "source"], how="left")
    missing = merged["text_en"].isna()

    if missing.any():
        tokenizer = MarianTokenizer.from_pretrained(MODEL)
        model = MarianMTModel.from_pretrained(MODEL)
        pieces = [(i, s) for i in merged.index[missing] for s in sentences(merged.at[i, "source"])]
        texts = [s for _, s in pieces]
        italian = [k for k, t in enumerate(texts) if is_italian(t) or merged.at[pieces[k][0], "kind"] != "startup_description"]
        translated = list(texts)
        to_do = [texts[k] for k in italian]
        done_batches = []
        for k in range(0, len(to_do), 16):
            batch = tokenizer(to_do[k:k + 16], return_tensors="pt", padding=True, truncation=True)
            done_batches += tokenizer.batch_decode(model.generate(**batch, num_beams=4, max_new_tokens=512),
                                                   skip_special_tokens=True)
        for k, t in zip(italian, done_batches):
            translated[k] = t
        joined = {}
        for (i, _), t in zip(pieces, translated):
            joined[i] = f"{joined.get(i, '')} {t}".strip()
        for i, t in joined.items():
            merged.at[i, "text_en"] = t
    merged["model"] = MODEL
    merged[COLUMNS].to_csv(OUT, index=False)

    print(f"texts to show in English: {len(merged)}  {merged['kind'].value_counts().to_dict()}")
    print(f"translated this run:      {int(missing.sum())} (others reused)")
    print(f"saved:                    {OUT}")


if __name__ == "__main__":
    main()
