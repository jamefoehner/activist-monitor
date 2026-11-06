"""Score the labeler against hand labels. Pure functions, no network."""
import random

from .labeler import FIELDS


def _zeros():
    return {f: 0 for f in FIELDS}


def effective(pred):
    """What the app would show: unparsed answers and 'not a demand' both mean no categories."""
    if pred is None or pred.get("not_a_demand"):
        return _zeros()
    return {f: int(pred[f]) for f in FIELDS}


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score(gold: list[dict], preds: list) -> dict:
    """gold: list of {field: 0/1}; preds: aligned list of label dicts or None."""
    eff = [effective(p) for p in preds]
    n = len(gold)
    fields, f1s = {}, []
    for f in FIELDS:
        tp = sum(g[f] and e[f] for g, e in zip(gold, eff))
        fp = sum((not g[f]) and e[f] for g, e in zip(gold, eff))
        fn = sum(g[f] and (not e[f]) for g, e in zip(gold, eff))
        p, r, f1 = _prf(tp, fp, fn)
        fields[f] = {"support": tp + fn, "precision": p, "recall": r, "f1": f1}
        f1s.append(f1)
    exact = sum(all(g[f] == e[f] for f in FIELDS) for g, e in zip(gold, eff)) / n
    return {"n": n, "macro_f1": sum(f1s) / len(f1s), "exact_match": exact, "fields": fields,
            "parse_rate": sum(p is not None for p in preds) / n,
            "not_a_demand_rate": sum(bool(p and p.get("not_a_demand")) for p in preds) / n}


def bootstrap_ci(gold, preds, metric, n_boot: int = 1000, seed: int = 0):
    """95% interval for score(...)[metric] by resampling filings with replacement."""
    rng, n, vals = random.Random(seed), len(gold), []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(score([gold[i] for i in idx], [preds[i] for i in idx])[metric])
    vals.sort()
    return vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]


def baselines(gold: list[dict]) -> dict:
    none = score(gold, [dict(_zeros(), not_a_demand=0)] * len(gold))
    eo = score(gold, [dict(_zeros(), engagement_only=1, not_a_demand=0)] * len(gold))
    return {"always_none": {"macro_f1": none["macro_f1"], "exact_match": none["exact_match"]},
            "always_engagement_only": {"macro_f1": eo["macro_f1"], "exact_match": eo["exact_match"]}}
