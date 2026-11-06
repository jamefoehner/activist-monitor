"""Activist Filing Monitor: streamlit run app.py"""
import html
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from monitor.data import (DATA, active_labels, load_campaigns, load_feed, load_scores, norm, past_campaigns,
                          recent_filings, search_companies)

st.set_page_config(page_title="Activist Filing Monitor", page_icon="📈", layout="wide")

NICE = {"board_seats": "Board seats", "sale_or_review": "Sale / review", "breakup_spin": "Breakup / spin-off",
        "capital_return": "Capital return", "operations_costs": "Operations / costs",
        "management_change": "Management change", "governance": "Governance", "oppose_deal": "Oppose deal",
        "capital_discipline": "Capital discipline", "engagement_only": "Engagement only"}
COLORS = {"board_seats": "#2f5bd3", "sale_or_review": "#b4492f", "breakup_spin": "#8a4fbf",
          "capital_return": "#1f7a5c", "operations_costs": "#a86a00", "management_change": "#c2255c",
          "governance": "#0b7285", "oppose_deal": "#7a3b2e", "capital_discipline": "#4a6b1f",
          "engagement_only": "#5d6470"}
ACTIVIST_NAMES = {"elliott": "Elliott", "starboard value": "Starboard", "icahn": "Icahn", "jana partners": "Jana",
                  "pershing square": "Pershing Square", "third point llc": "Third Point", "trian": "Trian",
                  "valueact": "ValueAct"}
EXAMPLES = ["Post Holdings", "Southwest Airlines", "Sonos", "Wendy's"]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input { font-family: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif; }
.block-container { max-width: 60rem; padding-top: 1.1rem; padding-bottom: 3rem; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }

.hero { padding: 0 0 .9rem; }
.hero .live { display: inline-flex; align-items: center; gap: .45rem; font-family: 'IBM Plex Mono', monospace;
              font-size: .7rem; letter-spacing: .06em; text-transform: uppercase; color: #5d6470; margin-bottom: .35rem; }
.hero .live i { width: 8px; height: 8px; border-radius: 50%; background: #1f9d6b; box-shadow: 0 0 0 3px #d8f0e5; }
.hero h1 { font-size: 2.05rem; line-height: 1.1; letter-spacing: -0.025em; margin: 0 0 .3rem; font-weight: 700; }
.hero p { color: #4a5260; font-size: 1rem; max-width: 44rem; margin: 0 0 .8rem; line-height: 1.45; }
.stats { display: flex; flex-wrap: wrap; gap: .35rem 1.4rem; padding: .55rem 0; border-top: 1px solid #e3e6ea;
         border-bottom: 1px solid #e3e6ea; }
.stat { display: inline-flex; align-items: baseline; gap: .4rem; }
.stat b { font-size: 1.05rem; font-weight: 500; font-family: 'IBM Plex Mono', monospace; color: #14171c; }
.stat span { font-size: .8rem; color: #5d6470; }
@media (max-width: 40rem) { .hero h1 { font-size: 1.7rem; } .hero p { font-size: .95rem; } .stats { display: grid; grid-template-columns: 1fr 1fr; gap: .25rem 1rem; } .stat b { font-size: .95rem; white-space: nowrap; } }

.card { border: 1px solid #e3e6ea; border-radius: 12px; padding: 1rem 1.2rem .9rem; margin: 0 0 .85rem; background: #fff;
        transition: box-shadow .15s, border-color .15s; }
.card:hover { box-shadow: 0 4px 18px rgba(20,23,28,.07); border-color: #cfd6e6; }
.card .top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .3rem 1rem; }
.card .who { font-weight: 600; font-size: .86rem; color: #2f5bd3; }
.card .form { font-family: 'IBM Plex Mono', monospace; font-size: .72rem; color: #5d6470; background: #eef0f3;
              border-radius: 4px; padding: .1rem .4rem; margin-left: .4rem; }
.card .date { font-size: .82rem; color: #5d6470; }
.card .name { font-weight: 600; font-size: 1.12rem; margin: .35rem 0 .6rem; letter-spacing: -0.01em; }
.card .foot { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.1rem; margin-top: .55rem;
              font-size: .84rem; color: #5d6470; }
.card .foot a { color: #2f5bd3; text-decoration: none; font-weight: 500; }
.card .foot a:hover { text-decoration: underline; }
.card details { margin-top: .5rem; }
.card summary { cursor: pointer; font-size: .84rem; font-weight: 500; color: #2f5bd3; list-style: none; }
.card summary::-webkit-details-marker { display: none; }
.card summary::before { content: "▸ "; }
.card details[open] summary::before { content: "▾ "; }
.card .item4 { margin-top: .6rem; padding: .8rem 1rem; background: #f6f7fa; border-radius: 8px; font-size: .86rem;
               line-height: 1.55; color: #2a3140; max-height: 22rem; overflow-y: auto; }
.pill { display: inline-block; font-size: .78rem; font-weight: 500; color: #fff; padding: .2rem .65rem;
        border-radius: 999px; margin: 0 .35rem .3rem 0; }
.pill.muted { background: #eef0f3; color: #5d6470; font-weight: 400; }
.chip { display: inline-block; font-size: .76rem; border: 1px solid #dbe1f1; background: #f3f6fd; color: #34508f;
        padding: .12rem .55rem; border-radius: 6px; }
.note { font-size: .88rem; color: #5d6470; }

.meter { background: #e9edf5; border-radius: 6px; height: 10px; position: relative; margin: .5rem 0 .4rem; }
.meter span { position: absolute; left: 0; top: 0; height: 10px; border-radius: 6px; background: linear-gradient(90deg, #c9d3ea, #2f5bd3); }
.scorebox { border: 1px solid #e3e6ea; border-radius: 12px; padding: 1.1rem 1.3rem; background: #fbfcfe; }
.scorebox .big { font-family: 'IBM Plex Mono', monospace; font-size: 2.6rem; font-weight: 500; color: #2f5bd3; line-height: 1; }
.reason { display: inline-block; background: #eef2fd; color: #2f5bd3; font-size: .85rem; padding: .25rem .65rem;
          border-radius: 6px; margin: 0 .4rem .4rem 0; }
.toplist, .history { width: 100%; border-collapse: collapse; font-size: .92rem; border: none !important; }
.toplist td, .history td, .history th { border-left: none !important; border-right: none !important; border-top: none !important; }
.toplist td { padding: .55rem .5rem; border-bottom: 1px solid #edf0f5 !important; vertical-align: middle; }
.toplist .rk { font-family: 'IBM Plex Mono', monospace; color: #5d6470; width: 2rem; }
.toplist .nm { font-weight: 600; }
.toplist .why { color: #5d6470; font-size: .84rem; }
.pos { color: #1f7a5c; font-weight: 500; } .neg { color: #b4492f; font-weight: 500; }
.history th { text-align: left; font-weight: 600; border-bottom: 2px solid #14171c !important; padding: .4rem .5rem; background: none !important; }
.history td { padding: .5rem; border-bottom: 1px solid #edf0f5 !important; }
.history .r { text-align: right; }
.disclaimer { font-size: .8rem; color: #5d6470; border-top: 1px solid #e3e6ea; margin-top: 2.5rem; padding-top: 1rem; }
div[data-testid="stSegmentedControl"] { margin: .2rem 0 .1rem; }
div[data-testid="stVerticalBlock"] { gap: .6rem; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- data
@st.cache_data
def scores():
    return load_scores()


@st.cache_data
def score_lookup():
    s = scores()
    return {k: (p, r) for k, p, r in zip(s["key"], s["score_pct"], s["rank"])}


@st.cache_data
def campaigns():
    return load_campaigns()


@st.cache_data
def load_eval():
    p = DATA / "eval_results.json"
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data(ttl=300)
def feed():
    return load_feed()


# ---------------------------------------------------------------- helpers
def wide(df, **kw):
    """Full-width dataframe across Streamlit versions (use_container_width was replaced by width)."""
    try:
        st.dataframe(df, width="stretch", **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, **kw)


def text_or_none(x):
    """A non-empty string, or None. Guards against NaN floats from missing values."""
    return x if isinstance(x, str) and x else None


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def fmt_date(s) -> str:
    try:
        d = datetime.strptime(str(s)[:10], "%Y-%m-%d")
        return f"{d:%b} {d.day}, {d.year}"
    except ValueError:
        return str(s)


KEEP_UPPER = {"LLC", "LP", "L.P.", "NV", "N.V.", "SA", "UK", "II", "III", "IV", "XI", "ETF", "REIT", "AI", "US", "USA"}
LEGAL = {"INC": "Inc", "INC.": "Inc.", "CORP": "Corp", "CORP.": "Corp.", "CO": "Co", "CO.": "Co.", "LTD": "Ltd",
         "LTD.": "Ltd.", "PLC": "plc", "THE": "the", "AND": "and", "OF": "of", "FOR": "for"}


def pretty(name: str) -> str:
    """'WENDY'S CO' -> "Wendy's Co". Keeps LLC, L.P. and short ticker-like words such as CVR in capitals."""
    words = []
    for i, w in enumerate(str(name).split()):
        u = w.upper().strip(",")
        if u in LEGAL and i > 0:
            words.append(LEGAL[u])
        elif u in KEEP_UPPER or (len(u) <= 3 and u.isalpha() and u not in LEGAL):
            words.append(u)
        else:
            words.append(w.title().replace("'S", "'s"))
    return " ".join(words)


def item4_html(text: str) -> str:
    # No blank lines and no raw "$": either one would make Streamlit's markdown parser interfere with the HTML block.
    t = esc(text[:3500]).replace("$", "&#36;")
    t = t.replace("\r", "").replace("\n\n", "<br><br>").replace("\n", "<br>")
    return t


def pills(labels) -> str:
    if not isinstance(labels, dict):
        return ""
    if labels.get("not_a_demand"):
        return '<span class="pill muted">No demand · administrative filing</span>'
    act = active_labels(labels)
    if not act:
        return '<span class="pill muted">No categories matched</span>'
    return "".join(f'<span class="pill" style="background:{COLORS.get(a, "#5d6470")}">{esc(NICE.get(a, a))}</span>'
                   for a in act)


STATUS_NOTE = {"no_item4": "This amendment does not amend Item 4, so there is nothing to label.",
               "skipped_not_activist": "Filed by someone who is not on the known-activist list, so it was not labeled.",
               "unparsed": "The model's answer could not be read.", "not_labeled": "Not labeled yet."}


def filing_card(r):
    activist = r.get("activist") if isinstance(r.get("activist"), str) else None
    filers = r.get("filers") if isinstance(r.get("filers"), list) else []
    who = ACTIVIST_NAMES.get(activist) or (pretty(filers[0]) if filers else "Unknown filer")
    subject = text_or_none(r.get("subject")) or r["title"]
    body = pills(r["labels"]) if r["label_status"] == "ok" else \
        f'<div class="note">{esc(STATUS_NOTE.get(r["label_status"], r["label_status"]))}</div>'
    sc = score_lookup().get(norm(subject))
    chip = f'<span class="chip">Target score {sc[0] * 100:.0f} · rank {int(sc[1]):,}</span>' if sc else ""
    item4 = text_or_none(r.get("item4_text"))
    details = (f'<details><summary>Read Item 4, the filer\'s stated purpose</summary>'
               f'<div class="item4">{item4_html(item4)}</div></details>') if item4 else ""
    form = str(r["form"]).replace("SCHEDULE ", "").replace("SC ", "")
    st.markdown(
        '<div class="card">'
        f'<div class="top"><div><span class="who">{esc(who)}</span><span class="form">{esc(form)}</span></div>'
        f'<span class="date">{esc(fmt_date(r["filed"]))}</span></div>'
        f'<div class="name">{esc(pretty(subject))}</div>{body}{details}'
        f'<div class="foot">{chip}<a href="{esc(r["link"])}" target="_blank" rel="noopener">View on EDGAR ↗</a></div>'
        '</div>', unsafe_allow_html=True)


def meter(pct: float) -> str:
    p = max(0.0, min(100.0, pct))
    return f'<div class="meter"><span style="width:{p}%"></span></div>'


def ret(x):
    if pd.isna(x):
        return "n/a"
    return f'<span class="{"pos" if x >= 0 else "neg"}">{x * 100:+.1f}%</span>'


def set_query(name: str):
    st.session_state["q"] = name


# ---------------------------------------------------------------- header
f_all = feed()
acts = f_all["activist"].dropna() if not f_all.empty else pd.Series(dtype=str)
updated = fmt_date(f_all["processed_at"].max()[:10]) if (not f_all.empty and "processed_at" in f_all) else "n/a"
st.markdown(f"""<div class="hero"><div class="live"><i></i>Updated daily from SEC EDGAR</div>
<h1>Activist Filing Monitor</h1>
<p>What activist investors are asking for in new SEC 13D filings, and which companies they are most likely to target next.</p>
<div class="stats">
<div class="stat"><b>{len(acts)}</b><span>activist filings</span></div>
<div class="stat"><b>{acts.nunique()}</b><span>activists</span></div>
<div class="stat"><b>{len(scores()):,}</b><span>companies scored</span></div>
<div class="stat"><b>{esc(updated)}</b><span>last updated</span></div>
</div></div>""", unsafe_allow_html=True)

SECTIONS = ["Latest filings", "Company lookup", "How it works"]
# A selector in session state instead of st.tabs: tabs snap back to the first one on every rerun.
section = st.segmented_control("Section", SECTIONS, default=SECTIONS[0], key="section",
                               label_visibility="collapsed") or SECTIONS[0]

# ---------------------------------------------------------------- latest filings
if section == SECTIONS[0]:
    if f_all.empty:
        st.info("No filings loaded yet. Run `python -m monitor.pipeline` to fetch some.")
    else:
        c1, c2, c3 = st.columns([2, 2, 1.6])
        who = sorted({a for a in f_all["activist"].dropna().unique()})
        names = {ACTIVIST_NAMES.get(w, w.title()): w for w in who}
        pick_who = c1.multiselect("Activist", list(names), placeholder="All activists", label_visibility="collapsed")
        pick_lab = c2.multiselect("Demand", list(NICE.values()), placeholder="Any demand", label_visibility="collapsed")
        everyone = c3.toggle("Include other filers", value=False,
                             help="Trusts, SPAC sponsors and holders that are not on the activist list")
        view = f_all if everyone else f_all[f_all["activist"].notna()]
        if pick_who:
            view = view[view["activist"].isin([names[p] for p in pick_who])]
        if pick_lab:
            inv = {v: k for k, v in NICE.items()}
            want = [inv[p] for p in pick_lab]
            view = view[view["labels"].map(lambda l: isinstance(l, dict) and any(l.get(w) for w in want))]
        st.caption(f"Showing {min(len(view), 50)} of {len(view)} filings, newest first")
        if view.empty:
            st.info("Nothing matches those filters.")
        for _, r in view.head(50).iterrows():
            filing_card(r)

# ---------------------------------------------------------------- company lookup
if section == SECTIONS[1]:
    q = st.text_input("Search a company", key="q", placeholder="Search any of 2,600 U.S. companies by name",
                      label_visibility="collapsed")
    if not q:
        st.markdown('<div class="note" style="margin:.2rem 0 .5rem">Try one:</div>', unsafe_allow_html=True)
        cols = st.columns([1.25, 1.6, 0.85, 1.0, 2.6])
        for col, name in zip(cols, EXAMPLES):
            col.button(name, on_click=set_query, args=(name,), key=f"ex-{name}")
        st.markdown("#### Highest-scoring companies right now")
        top = scores().nsmallest(8, "rank")
        rows = "".join(
            f'<tr><td class="rk">{int(r["rank"])}</td><td><div class="nm">{esc(pretty(r["conm"]))}</div>'
            f'<div class="why">{esc(r["top_reasons"])}</div></td>'
            f'<td style="text-align:right;white-space:nowrap" class="note">score {r["score_pct"]*100:.1f}</td></tr>'
            for _, r in top.iterrows())
        st.markdown(f'<table class="toplist">{rows}</table>', unsafe_allow_html=True)
    else:
        hits = search_companies(scores(), q)
        if hits.empty:
            st.info("No company with that name in the screener, which covers about 2,600 U.S. companies.")
        else:
            row = hits.iloc[0] if len(hits) == 1 else hits.iloc[
                st.selectbox("Matches", range(len(hits)), format_func=lambda i: pretty(hits.iloc[i]["conm"]))]
            pct = row["score_pct"] * 100
            reasons = [x.strip() for x in str(row["top_reasons"]).split(";") if x.strip()]
            c1, c2 = st.columns([1.1, 1.6])
            c1.markdown(f"""<div class="scorebox"><div class="note">Activist-target score</div>
              <div class="big">{pct:.1f}</div>{meter(pct)}
              <div class="note">percentile · rank {int(row['rank']):,} of {len(scores()):,}</div></div>""",
                        unsafe_allow_html=True)
            c2.markdown(f"""<h3 style="margin:.1rem 0 .3rem">{esc(pretty(row['conm']))}</h3>
              <div class="note" style="margin-bottom:.7rem">Ranked {int(row['rank']):,} of {len(scores()):,} companies</div>
              <div class="note" style="margin-bottom:.35rem">What the model sees:</div>
              {''.join(f'<span class="reason">{esc(r)}</span>' for r in reasons)}""", unsafe_allow_html=True)
            st.caption("The score comes from a gradient-boosting model on peer-relative financials, as of early "
                       "November 2026. In a walk-forward test (2016 to 2025) its top 10% caught about 27% of later "
                       "targets, versus 10% by chance.")

            st.markdown("#### Past activist campaigns here")
            pc = past_campaigns(campaigns(), row["key"])
            if pc.empty:
                st.markdown('<div class="note">None in the research data (8 major activists, 2010 to 2026).</div>',
                            unsafe_allow_html=True)
            else:
                rows = "".join(f"<tr><td>{esc(fmt_date(r.filed_date))}</td><td>{esc(str(r.activist))}</td>"
                               f'<td class="r">{ret(r.car_m1_p1)}</td><td class="r">{ret(r.car_m10_p20)}</td></tr>'
                               for r in pc.itertuples())
                st.markdown(f'<table class="history"><thead><tr><th>Filed</th><th>Activist</th>'
                            f'<th class="r">Return vs market, days 0 to 1</th><th class="r">Days −10 to +20</th></tr></thead>'
                            f'<tbody>{rows}</tbody></table>', unsafe_allow_html=True)

            st.markdown("#### Recent 13D filings")
            rf = recent_filings(f_all, row["key"])
            if rf.empty:
                st.markdown('<div class="note">None in the current feed.</div>', unsafe_allow_html=True)
            else:
                for _, r in rf.iterrows():
                    filing_card(r)

# ---------------------------------------------------------------- about
if section == SECTIONS[2]:
    st.markdown("""
### What this does
1. **Collects** new Schedule 13D filings from SEC EDGAR for a list of well-known activist investors.
2. **Extracts** Item 4, the section where the filer explains its purpose.
3. **Labels** it with up to ten demand categories (board seats, sale, buyback and so on) using Claude.
4. **Scores** every company on how much it resembles past activist targets.

### How far to trust it
- Treat each label as a draft and check the Item 4 text, which every card includes. Measured accuracy is in the section below.
- Only filings from the activist list are labeled. Trusts, SPAC sponsors and holders selling down are stored but skipped.
- Many amendments do not amend Item 4. Those show "nothing to label", which is different from "no demands".
- The "administrative filing" tag (share sales, distributions) is a recent addition and has not been evaluated.
- The score ranks companies against each other. It is not a prediction that any one company will be targeted.
""")
    ev = load_eval()
    st.markdown("#### Label accuracy on my hand-labeled test set")
    if ev is None:
        st.markdown('<div class="note">Not measured yet.</div>', unsafe_allow_html=True)
    else:
        e1, e2, e3 = st.columns(3)
        e1.metric("Macro-F1", f"{ev['macro_f1']:.2f}",
                  help=f"95% interval {ev['macro_f1_ci'][0]:.2f} to {ev['macro_f1_ci'][1]:.2f}. Averages the F1 of the ten categories equally.")
        e2.metric("All ten categories right", f"{ev['exact_match'] * 100:.0f}%",
                  help=f"95% interval {ev['exact_match_ci'][0] * 100:.0f}% to {ev['exact_match_ci'][1] * 100:.0f}%")
        b = ev["baselines"]["always_engagement_only"]["exact_match"]
        e3.metric("Guessing 'engagement only' every time", f"{b * 100:.0f}%", help="Exact-match rate of a constant answer")
        st.markdown(f"Tested on {ev['n']} hand-labeled filings with {ev['model']} on {ev['date']}. "
                    "Caveats: the test filings are original 13Ds, while most live filings are amendments, so live accuracy may differ; "
                    "and several categories have fewer than ten test examples.")
        fld = pd.DataFrame(ev["fields"]).T[["support", "precision", "recall", "f1"]].round(2)
        fld.index = [NICE.get(i, i) for i in fld.index]
        wide(fld.rename(columns={"support": "Test examples", "precision": "Precision", "recall": "Recall", "f1": "F1"}))
    try:
        m = pd.read_csv(DATA / "model_results.csv", index_col=0)
        m = m[["ROC AUC", "targets caught in top 10%"]].rename(index={"size_only": "Company size only",
              "logistic": "Logistic regression", "gbm": "Gradient boosting (used here)"},
              columns={"targets caught in top 10%": "Future targets caught in top 10%"})
        m["Future targets caught in top 10%"] = (m["Future targets caught in top 10%"] * 100).round(0).astype(int).astype(str) + "%"
        m["ROC AUC"] = m["ROC AUC"].round(2)
        st.markdown("#### Screener test results (walk-forward, 2016 to 2025)")
        wide(m)
    except Exception:
        pass
    st.markdown("Code and methods: [github.com/jamefoehner](https://github.com/jamefoehner)")

st.markdown('<div class="disclaimer">Independent student research project. Not investment advice. '
            'Data from SEC EDGAR, Compustat and CRSP via WRDS.</div>', unsafe_allow_html=True)
