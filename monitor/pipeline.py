"""Fetch recent 13D filings, extract Item 4, label the demands, append to data/feed.jsonl.

  export SEC_USER_AGENT="Your Name you@school.edu"
  export ANTHROPIC_API_KEY=...
  python -m monitor.pipeline --limit 20
  python -m monitor.pipeline --offline path/to/filing.txt      # no network: extract only, print Item 4
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .activists import load_patterns, match_activist
from .edgar import Edgar
from .extract import extract_item4, parse_header
from .labeler import Labeler

FEED_PATH = Path("data/feed.jsonl")


def load_ciks(path: Path = Path(__file__).resolve().parent.parent / "data" / "activist_ciks.csv") -> list[str]:
    import csv
    return [r["cik"] for r in csv.DictReader(path.open())]


def seen_accessions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(l)["accession"] for l in path.open() if l.strip()}


def process(entry: dict, raw: str, labeler: Labeler | None, patterns: list[str] | None = None,
            label_all: bool = False) -> dict:
    text, how = extract_item4(raw)
    hdr = parse_header(raw)
    activist = match_activist(hdr["filers"], patterns)
    rec = {**entry, "subject": hdr["subject"], "filers": hdr["filers"], "activist": activist,
           "item4_how": how, "item4_chars": len(text or ""), "item4_text": text,
           "labels": None, "label_status": "no_item4",
           "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if text and not activist and not label_all:
        rec["label_status"] = "skipped_not_activist"
    elif text and labeler:
        labels, _ = labeler.label(text)
        rec["labels"] = labels
        rec["label_status"] = "ok" if labels else "unparsed"
    elif text:
        rec["label_status"] = "not_labeled"
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--source", choices=["activists", "feed"], default="activists",
                    help="activists: ask EDGAR for each known activist's recent 13Ds (default); "
                         "feed: the all-filers 'current filings' feed, mostly non-activists")
    ap.add_argument("--days", type=int, default=60, help="activists source: look back this many days")
    ap.add_argument("--forms", nargs="+", default=["SCHEDULE 13D"], help="feed source only")
    ap.add_argument("--user-agent", default=None)
    ap.add_argument("--cache", default="cache/filings")
    ap.add_argument("--no-label", action="store_true", help="extract only; skip the Claude API")
    ap.add_argument("--label-all", action="store_true",
                    help="label every filing, not just those from known activists (costs more API calls)")
    ap.add_argument("--offline", help="extract Item 4 from one local filing file and print it")
    a = ap.parse_args(argv)

    if a.offline:
        text, how = extract_item4(Path(a.offline).read_text(encoding="latin-1"))
        print(f"[{how}] {len(text or '')} chars\n\n{(text or '')[:2000]}")
        return

    edgar = Edgar(a.user_agent, Path(a.cache))
    labeler = None if a.no_label else Labeler()
    patterns = load_patterns()
    done = seen_accessions(FEED_PATH)
    FEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    new = 0
    with FEED_PATH.open("a") as out:
        batches = ([edgar.activist_filings(load_ciks(), a.days)[: a.limit]] if a.source == "activists"
                   else [edgar.recent(form, count=a.limit) for form in a.forms])
        for batch in batches:
            for e in batch:
                if e["accession"] in done:  # the feed lists a filing once per party (filer and subject)
                    continue
                try:
                    rec = process(e, edgar.filing_text(e["accession"], e["cik"]), labeler, patterns, a.label_all)
                except Exception as ex:  # one bad filing shouldn't stop the run
                    cause = f" (cause: {ex.__cause__!r})" if ex.__cause__ else ""
                    print(f"skip {e['accession']}: {type(ex).__name__}: {ex}{cause}", file=sys.stderr)
                    done.add(e["accession"])
                    continue
                out.write(json.dumps(rec) + "\n")
                done.add(e["accession"]); new += 1
                who = rec["activist"] or "-"
                print(f"{e['accession']}  {(rec['subject'] or e['title'])[:34]:34s}  {who:16s}  {rec['label_status']}")
    print(f"{new} new filings (non-activist filers are stored but not labeled; use --label-all to change)")


if __name__ == "__main__":
    main()
