"""Score patent-startup similarity and write data/processed/edges_similarity.csv.

Cosine similarity between every patent and every startup embedding
(src/embed/embed.py). Pairs at or above `similarity.threshold` (config.yaml) become edges,
keeping at most `similarity.max_links_per_patent` startups per patent (the closest ones).

Each edge gets `top_terms`: single words and two-word phrases taken from either text that
are closest to BOTH texts (score = min of the two cosine similarities, computed with the
same multilingual model). They show what the match is about; they are an explanation aid,
not the cause of the score.

Edges whose patent has no abstract (text_source == "title" in patents.csv) are marked
`low_confidence`: a short title, often in Italian, gives unreliable scores (Italian-Italian
pairs score higher on average with this model).

Usage:
    python src/score/similarity.py [--top-terms N]
"""
import argparse
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sentence_transformers import SentenceTransformer

OUT = Path("data/processed/edges_similarity.csv")

STOPWORDS = set("""
a about above after again all also among an and any are as at be been being both but by can
could did do does doing during each either for from further had has have having here how if
in into is it its itself may more most must no nor not of on once only or other our out over
own same should so some such than that the their them then there these they this those
through to too under until up upon very was we were what when where which while who whom why
will with within without would you your
wherein whereby thereof therein said first second third least one two three means invention
device method system comprising comprises comprise provided least portion element elements
il lo la i gli le un uno una di da in con su per tra fra e ed o od ma se che chi cui non
del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle
nel nello nella nei negli nelle sul sullo sulla sui sugli sulle come anche più piu dove
quando questo questa questi queste quello quella sono essere è siamo nostro nostra nostri
nostre loro suo sua suoi sue ogni tutti tutte tutto molto ancora già sempre solo nuovo nuova
srl s.r.l spa s.p.a società societa azienda startup company italy italia italian milano milan
more learn read scopri discover our we us
""".split())

WORD = re.compile(r"[a-zà-ù][a-zà-ù\-]{2,}")


def candidate_terms(text):
    words = [w.strip("-") for w in WORD.findall(text.lower())]
    words = [w for w in words if len(w) >= 4 or w in {"ecg", "eeg", "mri", "dna", "rna"}]
    unigrams = [w for w in words if w not in STOPWORDS]
    bigrams = [f"{a} {b}" for a, b in zip(words, words[1:]) if a not in STOPWORDS and b not in STOPWORDS]
    return set(unigrams) | set(bigrams)


def load(emb_dir, name):
    df = pd.read_parquet(emb_dir / f"{name}.parquet")
    return df, np.vstack(df["embedding"].to_numpy())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-terms", type=int, default=5)
    args = parser.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    threshold = cfg["similarity"]["threshold"]
    model_name = cfg["embedding"]["model"]
    emb_dir = Path("data/processed/embeddings") / model_name.split("/")[-1]
    if not emb_dir.exists():
        raise SystemExit(f"No embeddings in {emb_dir}: run src/embed/embed.py first")
    patents, P = load(emb_dir, "patents")
    startups, S = load(emb_dir, "startups")

    text_source = pd.read_csv("data/processed/patents.csv", dtype=str).set_index("patent_id")["text_source"]

    # Explanatory terms are taken from the English texts (machine translations where the
    # original is Italian, src/clean/translate_en.py) so the site reads in one language.
    # Scores still come from the original texts.
    term_text_p, term_text_s = patents["text"].copy(), startups["text"].copy()
    translations = Path("data/processed/translations_en.csv")
    if translations.exists():
        tr = pd.read_csv(translations, dtype=str, keep_default_na=False)
        titles = tr[tr["kind"] == "patent_title"].set_index("key")["text_en"]
        descs = tr[tr["kind"] == "startup_description"].set_index("key")["text_en"]
        title_only = patents["id"].map(text_source) == "title"
        term_text_p = term_text_p.where(~(title_only & patents["id"].isin(titles.index)),
                                        patents["id"].map(titles))
        names = startups["text"].str.split(". ", n=1).str[0]
        term_text_s = term_text_s.where(~startups["id"].isin(descs.index),
                                        names + ". " + startups["id"].map(descs))

    sim = P @ S.T  # vectors are L2-normalised
    # Keep pairs at or above the threshold, and at most N startups per patent (its closest ones)
    max_per = cfg["similarity"].get("max_links_per_patent")
    keep = sim >= threshold
    if max_per:
        rank = (-sim).argsort(axis=1).argsort(axis=1)  # 0 = closest startup for each patent
        n_cut = int((keep & (rank >= max_per)).sum())
        keep &= rank < max_per
    pi, si = np.nonzero(keep)

    # Term embeddings, only for texts that take part in an edge
    model = SentenceTransformer(model_name)
    terms_of = {}
    for i in set(pi):
        terms_of[("p", i)] = candidate_terms(term_text_p.iloc[i])
    for j in set(si):
        terms_of[("s", j)] = candidate_terms(term_text_s.iloc[j])
    vocab = sorted(set().union(*terms_of.values())) if terms_of else []
    T = model.encode(vocab, batch_size=128, normalize_embeddings=True) if vocab else np.empty((0, P.shape[1]))
    index = {t: k for k, t in enumerate(vocab)}

    rows = []
    for i, j in zip(pi, si):
        terms = sorted(terms_of[("p", i)] | terms_of[("s", j)])
        V = T[[index[t] for t in terms]]
        both = np.minimum(V @ P[i], V @ S[j])
        top, seen = [], set()
        for k in np.argsort(-both):
            words = set(terms[k].split())
            if words & seen:
                continue  # avoid "cardiac" + "cardiac valve" + "valve"
            top.append(terms[k])
            seen |= words
            if len(top) == args.top_terms:
                break
        rows.append({
            "tech_id": patents["id"].iloc[i],
            "tech_type": "patent",
            "startup_id": startups["id"].iloc[j],
            "score": round(float(sim[i, j]), 4),
            "top_terms": "|".join(top),
            "tech_text_source": text_source[patents["id"].iloc[i]],
            "low_confidence": text_source[patents["id"].iloc[i]] == "title",
            "model": model_name,
            "run_date": date.today().isoformat(),
        })
    edges = pd.DataFrame(rows, columns=[
        "tech_id", "tech_type", "startup_id", "score", "top_terms", "tech_text_source", "low_confidence",
        "model", "run_date",
    ])
    edges = edges.sort_values("score", ascending=False)
    edges.to_csv(OUT, index=False)

    flat = sim.ravel()
    best_p, best_s = sim.max(axis=1), sim.max(axis=0)
    q = np.quantile(flat, [0.5, 0.9, 0.99, 0.999])
    print(f"patents x startups:        {sim.shape[0]} x {sim.shape[1]} = {flat.size} pairs")
    print(f"score quantiles 50/90/99/99.9%: {' / '.join(f'{x:.3f}' for x in q)}   max {flat.max():.3f}")
    if max_per:
        print(f"dropped by the {max_per}-per-patent cap: {n_cut}")
    print(f"edges >= {threshold}:             {len(edges)}  (low confidence, title only: {edges['low_confidence'].sum()})")
    print(f"patents with an edge:      {len(set(pi))} / {len(patents)}")
    print(f"startups with an edge:     {len(set(si))} / {len(startups)}")
    print("patents' best score:       " + "  ".join(
        f">={t}: {(best_p >= t).sum()}" for t in (0.4, 0.5, 0.55, 0.6, 0.65, 0.7)))
    print("startups' best score:      " + "  ".join(
        f">={t}: {(best_s >= t).sum()}" for t in (0.4, 0.5, 0.55, 0.6, 0.65, 0.7)))
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
