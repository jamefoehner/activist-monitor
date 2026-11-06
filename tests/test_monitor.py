import json
from pathlib import Path

import pytest

from monitor.edgar import parse_feed
from monitor.activists import match_activist
from monitor.extract import extract_item4, parse_header
from monitor.pipeline import process
from monitor.labeler import FIELDS, Labeler, parse_answer

FIX = Path(__file__).parent / "fixtures"


WITH_ITEM4 = ["0000902664-25-003788.txt", "0001013594-17-000046.txt"]


@pytest.mark.parametrize("name", WITH_ITEM4)
def test_extracts_item4_from_real_filings(name):
    text, how = extract_item4((FIX / name).read_text(encoding="latin-1"))
    assert text and len(text) > 100, how
    assert how != "not_found"


def test_amendment_that_does_not_amend_item4_returns_none():
    # Starboard's 13D/A for Alight (Dec 2025) is structured XML containing only items 1, 3, 5 and 7.
    # "No Item 4" is the correct answer there, and must not be read as "no demands".
    text, how = extract_item4((FIX / "0000921895-25-003291.txt").read_text(encoding="latin-1"))
    assert text is None and how == "xml_no_item4"


def test_extract_returns_none_when_missing():
    assert extract_item4("<DOCUMENT><TYPE>SC 13D<TEXT>nothing relevant here</TEXT>")[0] is None


def good(**kw):
    d = {f: 0 for f in FIELDS}; d.update(kw); return json.dumps(d)


def test_parse_ok():
    assert parse_answer("Sure: " + good(board_seats=1))["board_seats"] == 1


def test_parse_rejects_missing_key_and_bad_combo():
    assert parse_answer('{"board_seats": 1}') is None
    assert parse_answer(good(engagement_only=1, board_seats=1)) is None
    assert parse_answer("no json here") is None


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies); self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        block = type("B", (), {"type": "text", "text": self.replies.pop(0)})
        return type("M", (), {"content": [block]})


def test_labeler_retries_once_then_succeeds():
    c = FakeClient(["garbage", good(sale_or_review=1)])
    labels, _ = Labeler(c, model="x").label("text")
    assert labels["sale_or_review"] == 1 and c.calls == 2


def test_labeler_gives_up_after_retry():
    c = FakeClient(["garbage", "still garbage"])
    labels, raw = Labeler(c, model="x").label("text")
    assert labels is None and raw == "still garbage"


FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>SCHEDULE 13D - Acme Corp (0001234567) (Subject)</title>
<link href="https://www.sec.gov/Archives/edgar/data/1234567/000090266425003788/0000902664-25-003788-index.htm"/>
<updated>2026-11-04T16:01:00-05:00</updated></entry></feed>"""


def test_parse_feed():
    e = parse_feed(FEED)[0]
    assert e["accession"] == "0000902664-25-003788" and e["cik"] == "1234567"
    assert e["form"] == "SCHEDULE 13D" and e["filed"] == "2026-11-04"


def test_parse_header_names():
    h = parse_header((FIX / "0000921895-25-003291.txt").read_text(encoding="latin-1"))
    assert h["subject"].startswith("Alight") and h["filers"] == ["Starboard Value LP"]


@pytest.mark.parametrize("filer,expected", [
    ("ICAHN CARL C", "icahn"), ("Elliott Investment Management L.P.", "elliott"),
    ("MetLife Policyholder Trust", None), ("Delticus Holdings", None)])
def test_match_activist(filer, expected):
    assert match_activist([filer]) == expected


def test_activist_match_ignores_the_subject_company():
    # Third Point's own fund was the *subject* of a filing by someone else: not an activist campaign.
    assert match_activist(["Delticus Holdings"]) is None


def test_non_activist_is_not_labeled():
    raw = (FIX / "0000902664-25-003788.txt").read_text(encoding="latin-1").replace("Elliott Investment Management L.P.", "Some Trust")
    c = FakeClient([])
    rec = process({"accession": "x"}, raw, Labeler(c, model="x"))
    assert rec["label_status"] == "skipped_not_activist" and c.calls == 0


def test_activist_is_labeled():
    raw = (FIX / "0000902664-25-003788.txt").read_text(encoding="latin-1")
    rec = process({"accession": "x"}, raw, Labeler(FakeClient([good(engagement_only=1)]), model="x"))
    assert rec["activist"] == "elliott" and rec["label_status"] == "ok"


def test_not_a_demand_flag():
    d = json.loads(good()); d["not_a_demand"] = 1
    assert parse_answer(json.dumps(d))["not_a_demand"] == 1
    d["board_seats"] = 1
    assert parse_answer(json.dumps(d)) is None
    assert parse_answer(good(board_seats=1))["not_a_demand"] == 0


def test_load_feed_tolerates_old_rows(tmp_path):
    from monitor.data import load_feed
    f = tmp_path / "feed.jsonl"
    f.write_text(json.dumps({"accession": "a", "title": "SCHEDULE 13D/A - Acme Corp (0001234567) (Subject)",
                             "filed": "2026-11-05", "form": "SCHEDULE 13D/A", "link": "x",
                             "label_status": "ok", "labels": None}) + "\n")
    df = load_feed(f)
    assert df.loc[0, "subject"] == "Acme Corp" and df.loc[0, "key"] == "ACME"


def test_parse_submissions_filters_form_and_date():
    from monitor.edgar import parse_submissions
    data = {"cik": 1517137, "name": "Starboard Value LP", "filings": {"recent": {
        "form": ["SCHEDULE 13D/A", "4", "SC 13D", "SCHEDULE 13D"],
        "accessionNumber": ["0000921895-26-002935", "0000921895-26-000001", "0000921895-20-000001", "0000921895-26-000002"],
        "filingDate": ["2026-11-05", "2026-11-04", "2020-01-01", "2026-09-01"]}}}
    got = parse_submissions(data, since="2026-10-01")
    assert [g["accession"] for g in got] == ["0000921895-26-002935"]
    assert got[0]["cik"] == "0001517137" and got[0]["form"] == "SCHEDULE 13D/A"


def test_structured_filing_without_item4_does_not_return_other_items():
    # Elliott's Seadrill 13D/A (Oct 2026) contains only items 1, 3, 5 and 6. An earlier version of the
    # extractor returned a passage from Item 3 (margin accounts) via the loose heading fallback.
    text, how = extract_item4((FIX / "0000919574-26-006770.txt").read_text(encoding="latin-1"))
    assert text is None and how == "xml_no_item4"


def test_load_feed_missing_text_is_none_not_nan(tmp_path):
    import math
    from monitor.data import load_feed
    f = tmp_path / "feed.jsonl"
    rows = [{"accession": "a", "title": "SCHEDULE 13D - Acme Corp (0001234567) (Subject)", "filed": "2026-11-05",
             "form": "SCHEDULE 13D", "link": "x", "label_status": "no_item4", "labels": None, "item4_text": None},
            {"accession": "b", "title": "SCHEDULE 13D - Beta Inc (0007654321) (Subject)", "filed": "2026-11-04",
             "form": "SCHEDULE 13D", "link": "y", "label_status": "ok", "labels": {"board_seats": 1}, "item4_text": "text"}]
    f.write_text("\n".join(json.dumps(r) for r in rows))
    df = load_feed(f)
    v = df.loc[df["accession"] == "a", "item4_text"].iloc[0]
    assert v is None or not (isinstance(v, float) and math.isnan(v))
    assert v is None


def test_app_renders_filings_without_item4():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=60).run()
    assert not at.exception


def test_evaluate_scores_and_not_a_demand_counts_as_no_labels():
    from monitor.evaluate import baselines, bootstrap_ci, score
    gold = [dict.fromkeys(FIELDS, 0) | {"board_seats": 1}, dict.fromkeys(FIELDS, 0) | {"engagement_only": 1}]
    good_pred = [dict.fromkeys(FIELDS, 0) | {"board_seats": 1, "not_a_demand": 0},
                 dict.fromkeys(FIELDS, 0) | {"engagement_only": 1, "not_a_demand": 0}]
    s = score(gold, good_pred)
    assert s["exact_match"] == 1.0 and s["fields"]["board_seats"]["f1"] == 1.0
    # an answer that fires not_a_demand shows no categories, so it misses the true label
    nad = [dict.fromkeys(FIELDS, 0) | {"not_a_demand": 1}] * 2
    s2 = score(gold, nad)
    assert s2["exact_match"] == 0.0 and s2["not_a_demand_rate"] == 1.0
    assert score(gold, [None, None])["parse_rate"] == 0.0
    lo, hi = bootstrap_ci(gold, good_pred, "exact_match", n_boot=50)
    assert lo == hi == 1.0
    b = baselines(gold)
    assert b["always_engagement_only"]["exact_match"] == 0.5


def test_parse_finds_json_after_reasoning_prose():
    prose = 'The filers want to talk to management, which is only engagement. {"note": 1} Final: ' + good(engagement_only=1)
    assert parse_answer(prose)["engagement_only"] == 1
    assert parse_answer("Reasoning with no answer at all, then it was cut off mid-sent") is None


def test_labeler_uses_a_reply_limit_big_enough_for_reasoning():
    seen = {}
    class C(FakeClient):
        def create(self, **kw):
            seen.update(kw); return super().create(**kw)
    Labeler(C([good(board_seats=1)]), model="x").label("text")
    assert seen["max_tokens"] >= 800
