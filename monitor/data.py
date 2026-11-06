"""Load the screener scores, past campaigns and the live filing feed, and join them by company name."""
import json
import re
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
SUFFIXES = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "LLC", "LP", "PLC", "HOLDINGS",
            "HLDGS", "GROUP", "THE", "NV", "SA", "DE", "DELAWARE", "NEW"}


def norm(name) -> str:
    """Normalize a company name for matching: uppercase, no punctuation, no legal suffixes."""
    s = re.sub(r"[^A-Z0-9 ]", " ", str(name or "").upper().replace("&", " AND "))
    return " ".join(w for w in s.split() if w not in SUFFIXES)


def load_scores(path: Path = DATA / "scores_current.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    df["key"] = df["conm"].map(norm)
    df["rank"] = df["score_pct"].rank(ascending=False, method="min").astype(int)
    return df


def load_campaigns(path: Path = DATA / "event_study_results.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    df["key"] = df["subject_name"].map(norm)
    return df


def load_feed(path: Path = DATA / "feed.jsonl") -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    rows = [json.loads(l) for l in Path(path).open() if l.strip()]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Rows written by older pipeline versions lack these columns; fill them in rather than crash.
    for col, default in [("subject", None), ("activist", None), ("filers", None), ("labels", None),
                         ("item4_text", None), ("label_status", "not_labeled")]:
        if col not in df:
            df[col] = default
    df["subject"] = df["subject"].fillna(df["title"].str.extract(r" - (.+?) \(\d{6,}\)")[0])
    df["key"] = df["subject"].fillna("").map(norm)
    # Some pandas versions turn missing text into NaN (a truthy float). Use None so `if value:` works.
    df = df.astype(object).where(df.notna(), None)
    return df.sort_values("filed", ascending=False).reset_index(drop=True)


def search_companies(scores: pd.DataFrame, query: str, n: int = 10) -> pd.DataFrame:
    q = norm(query)
    if not q:
        return scores.iloc[0:0]
    hit = scores[scores["key"].str.contains(re.escape(q), na=False)]
    # exact matches first, then by score
    return hit.assign(_exact=(hit["key"] == q)).sort_values(["_exact", "score_pct"], ascending=[False, False]).head(n)


def past_campaigns(campaigns: pd.DataFrame, key: str) -> pd.DataFrame:
    return campaigns[campaigns["key"] == key].sort_values("filed_date", ascending=False)


def recent_filings(feed: pd.DataFrame, key: str) -> pd.DataFrame:
    if feed.empty:
        return feed
    return feed[feed["key"] == key]


def active_labels(labels) -> list[str]:
    if not isinstance(labels, dict):
        return []
    return [k for k, v in labels.items() if v and k != "not_a_demand"]
