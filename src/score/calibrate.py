"""Compare embedding models and calibrate the similarity threshold on hand-labelled pairs.

1. Export candidate pairs to label (union of each model's top pairs plus a random sample
   from the middle of the score range, so both sides of a threshold are represented):
       python src/score/calibrate.py export MODEL [MODEL ...]
   -> data/manual/calibration_pairs.csv with an empty `label` column. Scores are not
      written to the file, so labelling is blind to them.
   Label: 1 = the patent's technology is in the same specific field as the startup's
   product (same clinical problem or same device type, a licensing conversation would make
   sense); 0 = otherwise, including "both are medical but unrelated".

2. Compare models and pick thresholds:
       python src/score/calibrate.py report MODEL [MODEL ...]
   Prints, per model: score distribution by language pair (a fixed threshold is only fair
   if languages do not shift scores), rank agreement between models, and on the labelled
   pairs precision / recall / F1 at each threshold plus the best-F1 threshold.
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

EMB_ROOT = Path("data/processed/embeddings")
PAIRS = Path("data/manual/calibration_pairs.csv")
REPORT = Path("data/processed/calibration_report.json")
TOP_N = 40
N_MIDDLE = 40
ITALIAN = re.compile(r"\b(per|della|delle|degli|dei|che|il|una|sono|nella|sul|dispositivo|metodo)\b", re.I)


def load(model):
    d = EMB_ROOT / model.split("/")[-1]
    p = pd.read_parquet(d / "patents.parquet")
    s = pd.read_parquet(d / "startups.parquet")
    return p, s, np.vstack(p["embedding"].to_numpy()) @ np.vstack(s["embedding"].to_numpy()).T


def is_italian(texts):
    return texts.map(lambda t: len(ITALIAN.findall(t)) / max(len(t.split()), 1) > 0.04).to_numpy()


def export(models):
    rng = np.random.default_rng(0)
    pairs = set()
    for m in models:
        p, s, sim = load(m)
        flat = np.argsort(-sim, axis=None)
        for k in flat[:TOP_N]:
            i, j = np.unravel_index(k, sim.shape)
            pairs.add((p["id"].iloc[i], s["id"].iloc[j]))
        lo, hi = np.quantile(sim, [0.95, 0.995])
        middle = np.argwhere((sim >= lo) & (sim < hi))
        for i, j in middle[rng.choice(len(middle), size=min(N_MIDDLE, len(middle)), replace=False)]:
            pairs.add((p["id"].iloc[i], s["id"].iloc[j]))
    texts_p = p.set_index("id")["text"]
    texts_s = s.set_index("id")["text"]
    out = pd.DataFrame(sorted(pairs), columns=["patent_id", "vat_number"])
    out = out.sample(frac=1, random_state=0)  # no ordering hint
    out["patent_text"] = out["patent_id"].map(texts_p).str[:600]
    out["startup_text"] = out["vat_number"].map(texts_s).str[:600]
    out["label"] = ""
    out["note"] = ""
    PAIRS.parent.mkdir(parents=True, exist_ok=True)
    if PAIRS.exists():
        raise SystemExit(f"{PAIRS} exists: delete it first to export a new set")
    out.to_csv(PAIRS, index=False)
    print(f"exported {len(out)} pairs -> {PAIRS}")


def report(models):
    sims = {}
    for m in models:
        p, s, sim = load(m)
        sims[m] = (p, s, sim)
        it_p, it_s = is_italian(p["text"]), is_italian(s["text"])
        print(f"\n== {m}")
        print(f"   quantiles 50/90/99/99.9%: "
              + " / ".join(f"{x:.3f}" for x in np.quantile(sim, [0.5, 0.9, 0.99, 0.999])) + f"   max {sim.max():.3f}")
        for pn, pm in [("IT", it_p), ("EN", ~it_p)]:
            for sn, sm in [("IT", it_s), ("EN", ~it_s)]:
                sub = sim[np.ix_(pm, sm)]
                print(f"   patent {pn} x startup {sn}: n={sub.size:5}  mean={sub.mean():.3f}  p99={np.quantile(sub, .99):.3f}")

    if len(models) > 1:
        a, b = sims[models[0]][2].ravel(), sims[models[1]][2].ravel()
        rho = pd.Series(a).rank().corr(pd.Series(b).rank())
        top_a, top_b = set(np.argsort(-a)[:50]), set(np.argsort(-b)[:50])
        print(f"\nrank correlation (Spearman) {models[0]} vs {models[1]}: {rho:.3f}")
        print(f"overlap of top-50 pairs: {len(top_a & top_b)}/50")

    if not PAIRS.exists():
        return
    lab = pd.read_csv(PAIRS, dtype=str, keep_default_na=False)
    lab = lab[lab["label"].isin(["0", "1"])]
    if lab.empty:
        return
    y = lab["label"].astype(int).to_numpy()
    print(f"\nlabelled pairs: {len(lab)}  (positive: {y.sum()})")
    summary = {"labelled_pairs": len(lab), "positive": int(y.sum()), "models": {}}
    for m in models:
        p, s, sim = sims[m]
        pi = p.reset_index().set_index("id")["index"]
        si = s.reset_index().set_index("id")["index"]
        score = sim[pi[lab["patent_id"]].to_numpy(), si[lab["vat_number"]].to_numpy()]
        rows = []
        for t in np.round(np.arange(0.30, 0.85, 0.01), 2):
            pred = score >= t
            tp = (pred & (y == 1)).sum()
            prec = tp / pred.sum() if pred.sum() else np.nan
            rec = tp / y.sum()
            f1 = 2 * prec * rec / (prec + rec) if prec and rec else 0
            rows.append((t, pred.sum(), prec, rec, f1))
        res = pd.DataFrame(rows, columns=["threshold", "predicted", "precision", "recall", "f1"])
        best = res.loc[res["f1"].idxmax()]
        auc = pd.Series(score[y == 1]).apply(lambda v: (v > score[y == 0]).mean()).mean()
        print(f"\n== {m}   AUC (positive scored above negative): {auc:.3f}")
        print(res[res["predicted"] > 0].iloc[::3].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
        print(f"   best F1 {best.f1:.2f} at threshold {best.threshold:.2f} "
              f"(precision {best.precision:.2f}, recall {best.recall:.2f})")
        summary["models"][m] = {"auc": round(float(auc), 3), "best_threshold": float(best.threshold),
                                "best_f1": round(float(best.f1), 3)}
    # Read by src/build/site.py so the page quotes the comparison instead of hard-coded numbers
    REPORT.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nsaved: {REPORT}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "report"])
    parser.add_argument("models", nargs="+")
    args = parser.parse_args()
    (export if args.action == "export" else report)(args.models)


if __name__ == "__main__":
    main()
