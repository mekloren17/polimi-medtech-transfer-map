"""Machine-translate the Italian texts shown on the site into English.

Texts: startup descriptions, patent titles and patent abstracts (sector labels use the
official English NACE names instead, see src/build/site.py).
Abstracts lose the French paragraph that EPO adds to some WO filings. Descriptions and
abstracts are translated sentence by sentence: sentences that look Italian
are translated, English ones are kept, so bilingual texts work too. Titles are translated
whole. A sentence looks Italian when it has more Italian than English function words, or no
English function words and mostly words ending in -a, -i, -o ("Sistemi in produzione in
stabilimenti reali.").
Model: Helsinki-NLP/opus-mt-it-en (MarianMT), run locally; texts are not sent anywhere.
Texts the model cannot handle (e.g. a title in Spanish) are translated by hand in
data/manual/translations_en.csv (kind, key, text_en), which takes precedence.

Output: data/processed/translations_en.csv (kind, key, source, text_en, model). Rows whose
source text is unchanged and whose translation has no Italian sentence left are reused, so a
rerun only translates new or edited texts.
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
MANUAL = Path("data/manual/translations_en.csv")
MODEL = "Helsinki-NLP/opus-mt-it-en"
COLUMNS = ["kind", "key", "source", "text_en", "model"]
SENTENCE_LEVEL = {"startup_description", "patent_abstract"}

# Italian function words that are not also English words
IT_WORDS = re.compile(r"\b(il|lo|la|di|che|per|della|delle|dei|degli|con|una|uno|un|sono|nel|nella|alla|"
                      r"del|gli|le|i|e|ed|da|tra|al|ai|dal|dalla|sul|sulla|nei|sui|non|più|ci|si|mi|ti|ma|"
                      r"cosa|senza|nessun|nessuna|ogni|anche|come|quando|perché|è|nostro|nostra|nostri|"
                      r"nostre|tuo|tua|tuoi|tue|siamo|dispositivo|sistema|metodo)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|of|for|with|to|is|are|our|we|an|on|by|from|that|this|your|you|it|as|"
                      r"at|be|or|can|its)\b", re.I)
FR_WORDS = re.compile(r"\b(le|les|des|du|une|est|et|dans|pour|par|ladite|ledit|lesdits|lesdites|selon|"
                      r"qui|sur|au|aux|cette|ces|comprenant|présente|procédé)\b", re.I)
WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
PARAGRAPH = re.compile(r"\s*\[\d{4}\]\s*")


def is_italian(text):
    it, en, fr = (len(r.findall(text)) for r in (IT_WORDS, EN_WORDS, FR_WORDS))
    if fr > it:
        return False
    if it > en:
        return True
    # No function words at all: Italian words mostly end in -a, -i, -o; English and French rarely do
    words = WORD.findall(text)
    return en == 0 and len(words) >= 2 and sum(w[-1].lower() in "aioàìò" for w in words) >= 0.5 * len(words)


def drop_french(abstract):
    """EPO abstracts of WO filings often repeat the English text in French as a second
    numbered paragraph ([0001] English, [0002] French): keep the non-French paragraphs."""
    parts = [p for p in PARAGRAPH.split(abstract) if p.strip()]
    if len(parts) < 2:
        return abstract
    keep = [p for p in parts if len(FR_WORDS.findall(p)) <= len(EN_WORDS.findall(p))]
    return " ".join(keep) if keep else abstract


def sentences(text):
    """One piece per sentence: the language is decided per sentence, and pieces stay well
    inside the model's 512-token limit (descriptions are capped at about 600 characters)."""
    return [p for p in re.split(r"(?<=[.!?;])\s+|\s+(?=[“\"][A-Z])", text.strip()) if p]


def has_italian(text):
    return any(is_italian(s) for s in sentences(text))


def collect():
    startups = pd.read_csv(PROCESSED / "startups.csv", dtype=str, keep_default_na=False)
    patents = pd.read_csv(PROCESSED / "patents.csv", dtype=str, keep_default_na=False)
    manual = set()
    if MANUAL.exists():
        m = pd.read_csv(MANUAL, dtype=str, keep_default_na=False)
        manual = set(zip(m["kind"], m["key"]))
    rows = []
    for r in startups.itertuples():
        if r.description and (has_italian(r.description) or ("startup_description", r.vat_number) in manual):
            rows.append(("startup_description", r.vat_number, r.description))
    for r in patents.itertuples():
        title = r.title.capitalize() if r.title.isupper() else r.title
        if is_italian(title) or ("patent_title", r.patent_id) in manual:
            rows.append(("patent_title", r.patent_id, title))
        if r.abstract and (drop_french(r.abstract) != r.abstract or has_italian(r.abstract)
                           or ("patent_abstract", r.patent_id) in manual):
            rows.append(("patent_abstract", r.patent_id, r.abstract))
    return pd.DataFrame(rows, columns=["kind", "key", "source"])


def translate(texts):
    tokenizer = MarianTokenizer.from_pretrained(MODEL)
    model = MarianMTModel.from_pretrained(MODEL)
    out = []
    for k in range(0, len(texts), 16):
        batch = tokenizer(texts[k:k + 16], return_tensors="pt", padding=True, truncation=True)
        out += tokenizer.batch_decode(model.generate(**batch, num_beams=4, max_new_tokens=512),
                                      skip_special_tokens=True)
    return out


def main():
    todo = collect()
    done = pd.read_csv(OUT, dtype=str, keep_default_na=False) if OUT.exists() else pd.DataFrame(columns=COLUMNS)
    merged = todo.merge(done[["kind", "key", "source", "text_en"]], on=["kind", "key", "source"], how="left")
    missing = merged["text_en"].isna() | merged["text_en"].fillna("").map(
        lambda t: has_italian(t) if t else False)

    if missing.any():
        def prepared(i):
            src = merged.at[i, "source"]
            return drop_french(src) if merged.at[i, "kind"] == "patent_abstract" else src
        pieces = [(i, s) for i in merged.index[missing] for s in sentences(prepared(i))]
        texts = [s for _, s in pieces]
        italian = [k for k, t in enumerate(texts)
                   if is_italian(t) or merged.at[pieces[k][0], "kind"] not in SENTENCE_LEVEL]
        translated = list(texts)
        for k, t in zip(italian, translate([texts[k] for k in italian])):
            translated[k] = t
        joined = {}
        for (i, _), t in zip(pieces, translated):
            joined[i] = f"{joined.get(i, '')} {t}".strip()
        for i, t in joined.items():
            merged.at[i, "text_en"] = t
    merged["model"] = MODEL

    if MANUAL.exists():
        manual = pd.read_csv(MANUAL, dtype=str, keep_default_na=False).set_index(["kind", "key"])["text_en"]
        for i in merged.index:
            k = (merged.at[i, "kind"], merged.at[i, "key"])
            if k in manual.index:
                merged.at[i, "text_en"], merged.at[i, "model"] = manual[k], "manual"

    merged[COLUMNS].to_csv(OUT, index=False)
    left = merged[merged["text_en"].map(has_italian)]
    print(f"texts to show in English: {len(merged)}  {merged['kind'].value_counts().to_dict()}")
    print(f"translated this run:      {int(missing.sum())} (others reused)")
    print(f"to look at by hand:       {len(left)} {left['key'].tolist()[:10]} (often names or addresses)")
    print(f"saved:                    {OUT}")


if __name__ == "__main__":
    main()
