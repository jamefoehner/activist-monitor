"""Run the app's labeler on hand-labeled filings and write data/eval_results.json.

  export ANTHROPIC_API_KEY=...
  python scripts/eval_labeler.py                       # all 89 gold filings, about 2 minutes
  python scripts/eval_labeler.py --limit 10            # quick check

Replies are cached in data/eval_cache.jsonl, so re-running costs nothing for finished filings.
Gold file: one JSON per line with "id", "text" (Item 4) and "label" (the ten 0/1 fields).
"""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from monitor.evaluate import baselines, bootstrap_ci, score  # noqa: E402
from monitor.labeler import FIELDS, GUIDE, Labeler, parse_answer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--gold", default=str(Path.home() / "activist-project" / "data" / "rl" / "test_gold.jsonl"))
ap.add_argument("--model", default=None)
ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--out", default=str(ROOT / "data" / "eval_results.json"))
ap.add_argument("--workers", type=int, default=4)
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.gold) if l.strip()][: a.limit]
labeler = Labeler(model=a.model)
cache_path = ROOT / "data" / "eval_cache.jsonl"
cache = {}
if cache_path.exists():
    for l in cache_path.open():
        c = json.loads(l); cache[(c["model"], c["id"])] = c["raw"]


def run(row):
    key = (labeler.model, row["id"])
    if key in cache and parse_answer(cache[key]) is not None:   # re-ask only the ones that failed
        return row["id"], cache[key]
    _, raw = labeler.label(row["text"])
    return row["id"], raw


with ThreadPoolExecutor(a.workers) as ex:
    results = list(ex.map(run, rows))
with cache_path.open("a") as fh:
    for rid, raw in results:
        if cache.get((labeler.model, rid)) != raw:
            fh.write(json.dumps({"model": labeler.model, "id": rid, "raw": raw}) + "\n")

preds = [parse_answer(raw) for _, raw in results]
gold = [{f: int(r["label"][f]) for f in FIELDS} for r in rows]
s = score(gold, preds)
lo_f, hi_f = bootstrap_ci(gold, preds, "macro_f1")
lo_e, hi_e = bootstrap_ci(gold, preds, "exact_match")
out = {"model": labeler.model, "date": date.today().isoformat(), "n": s["n"],
       "prompt_sha": hashlib.sha256(GUIDE.encode()).hexdigest()[:10],
       "macro_f1": s["macro_f1"], "macro_f1_ci": [lo_f, hi_f],
       "exact_match": s["exact_match"], "exact_match_ci": [lo_e, hi_e],
       "parse_rate": s["parse_rate"], "not_a_demand_rate": s["not_a_demand_rate"],
       "fields": s["fields"], "baselines": baselines(gold),
       "gold_note": "89 hand-labeled original 13Ds from eight activists, 2010-2026"}
Path(a.out).write_text(json.dumps(out, indent=1))
print(f"n={s['n']}  macro-F1={s['macro_f1']:.3f} [{lo_f:.3f}, {hi_f:.3f}]  exact={s['exact_match']:.3f} "
      f"[{lo_e:.3f}, {hi_e:.3f}]  parsed={s['parse_rate']:.0%}  not_a_demand fired on {s['not_a_demand_rate']:.0%}")
for f, m in s["fields"].items():
    print(f"  {f:20s} support={m['support']:3d}  P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}")
print("baselines:", {k: {m: round(v, 3) for m, v in d.items()} for k, d in out["baselines"].items()})
print("wrote", a.out)
