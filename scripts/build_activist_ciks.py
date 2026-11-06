"""Collect the EDGAR CIKs of known-activist filers from cached 13D filings' SGML headers.

  python scripts/build_activist_ciks.py /path/to/cache/filings
Writes data/activist_ciks.csv (cik, name, pattern). Names are matched with data/activists.txt.
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitor.activists import load_patterns, match_activist  # noqa: E402

folder = Path(sys.argv[1])
patterns = load_patterns()
found = {}
for f in folder.glob("*.txt"):
    head = f.read_text(encoding="latin-1").split("</SEC-HEADER>", 1)[0]
    for block in re.split(r"^FILED BY:\s*$", head, flags=re.M)[1:]:
        block = re.split(r"^(?:SUBJECT COMPANY:|FILED BY:)\s*$", block, flags=re.M)[0]
        n = re.search(r"COMPANY CONFORMED NAME:\s*(.+)", block)
        c = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", block)
        if n and c:
            pat = match_activist([n.group(1)], patterns)
            if pat:
                found[c.group(1).zfill(10)] = (n.group(1).strip(), pat)
out = Path(__file__).resolve().parent.parent / "data" / "activist_ciks.csv"
with out.open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cik", "name", "pattern"])
    for cik, (name, pat) in sorted(found.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        w.writerow([cik, name, pat])
print(f"{len(found)} activist filer CIKs -> {out}")
