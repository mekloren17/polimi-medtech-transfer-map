"""Embed patent and startup texts with the multilingual model set in config.yaml.

Inputs:  data/processed/patents.csv  (text_for_embedding)
         data/processed/startups.csv (name + description; startups without a
         description are skipped: a company name alone says nothing about the technology)
Outputs: data/processed/embeddings/patents.parquet
         data/processed/embeddings/startups.parquet
Each row: id, text, model, run_date, embedding (L2-normalised float32 list).
The embeddings are reproducible from the tables above and are not committed.

Usage:
    python src/embed/embed.py
"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sentence_transformers import SentenceTransformer

PROCESSED = Path("data/processed")
OUT_DIR = PROCESSED / "embeddings"


def load_texts():
    patents = pd.read_csv(PROCESSED / "patents.csv", dtype=str, keep_default_na=False)
    patents = patents.rename(columns={"patent_id": "id", "text_for_embedding": "text"})[["id", "text"]]

    startups = pd.read_csv(PROCESSED / "startups.csv", dtype=str, keep_default_na=False)
    n_startups = len(startups)
    startups = startups[startups["description"] != ""]
    # The name often carries the product or field ("... Therapeutics", "... Medtech")
    startups = startups.assign(text=startups["name"].str.strip() + ". " + startups["description"])
    startups = startups.rename(columns={"vat_number": "id"})[["id", "text"]]
    return patents, startups, n_startups


def embed(model, df, model_name):
    vectors = model.encode(df["text"].tolist(), batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return df.assign(
        model=model_name,
        run_date=date.today().isoformat(),
        embedding=list(vectors.astype(np.float32)),
    )


def main():
    model_name = yaml.safe_load(open("config.yaml", encoding="utf-8"))["embedding"]["model"]
    patents, startups, n_startups = load_texts()
    model = SentenceTransformer(model_name)
    max_tokens = model.max_seq_length

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for label, df in [("patents", patents), ("startups", startups)]:
        out = embed(model, df, model_name)
        out.to_parquet(OUT_DIR / f"{label}.parquet", index=False)
        n_tokens = [len(model.tokenizer.tokenize(t)) for t in df["text"]]
        truncated = sum(n > max_tokens for n in n_tokens)
        print(f"{label:9} embedded: {len(out):4}  dim: {len(out['embedding'].iloc[0])}  "
              f"truncated at {max_tokens} tokens: {truncated}")
    print(f"startups skipped (no description): {n_startups - len(startups)}")
    print(f"model: {model_name}")
    print(f"saved: {OUT_DIR}/")


if __name__ == "__main__":
    main()
