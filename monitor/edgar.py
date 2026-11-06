"""Minimal EDGAR client: list recent 13D filings and download a filing's full text.

SEC rules: send a User-Agent that names you and gives an email, and stay under 10 requests/second.
Set SEC_USER_AGENT, for example "Jane Doe jane@school.edu". Downloads are cached on disk.
"""
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ATOM = "{http://www.w3.org/2005/Atom}"
FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}"
        "&company=&dateb=&owner=include&start={start}&count={count}&output=atom")
ACCESSION = re.compile(r"(\d{10})-?(\d{2})-?(\d{6})")


def parse_feed(xml_text: str) -> list[dict]:
    """Parse EDGAR's 'current filings' Atom feed into dicts (form, title, filed, accession, cik, link)."""
    out = []
    for e in ET.fromstring(xml_text).findall(f"{ATOM}entry"):
        link = e.find(f"{ATOM}link").get("href", "")
        title = e.findtext(f"{ATOM}title", "")
        m = ACCESSION.search(link)
        c = re.search(r"/data/(\d+)/", link)
        if not (m and c):
            continue
        form = title.split(" - ")[0].strip()
        out.append({
            "form": form,
            "title": title,
            "filed": (e.findtext(f"{ATOM}updated", "") or "")[:10],
            "accession": "-".join(m.groups()),
            "cik": c.group(1),
            "link": link,
        })
    return out


def parse_submissions(data: dict, since: str, name: str = "") -> list[dict]:
    """Pick 13D / 13D-A filings filed on or after `since` (YYYY-MM-DD) from a data.sec.gov submissions JSON."""
    r = data.get("filings", {}).get("recent", {})
    cik = str(data.get("cik", "")).zfill(10)
    out = []
    for form, acc, filed in zip(r.get("form", []), r.get("accessionNumber", []), r.get("filingDate", [])):
        if not form.upper().startswith(("SC 13D", "SCHEDULE 13D")) or filed < since:
            continue
        out.append({"form": form, "title": f"{form} - {data.get('name') or name} ({cik}) (Filed by)",
                    "filed": filed, "accession": acc, "cik": cik,
                    "link": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"})
    return out


class Edgar:
    def __init__(self, user_agent: str | None, cache: Path):
        ua = user_agent or os.environ.get("SEC_USER_AGENT", "")
        if "@" not in ua:
            raise SystemExit("Set SEC_USER_AGENT to something like 'Jane Doe jane@school.edu' "
                             "(the SEC requires a contact email).")
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.last = 0.0

    def _get(self, url: str) -> requests.Response:
        for attempt in range(5):
            wait = 0.15 - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.s.get(url, timeout=60)
            except requests.RequestException:
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                return r
            time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"failed to fetch {url}")

    def recent(self, form: str = "SCHEDULE 13D", count: int = 40) -> list[dict]:
        url = FEED.format(form=form.replace(" ", "+"), start=0, count=count)
        return parse_feed(self._get(url).text)

    def filing_text(self, accession: str, cik: str) -> str:
        f = self.cache / f"{accession}.txt"
        if f.exists():
            return f.read_text(encoding="latin-1")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}.txt"
        text = self._get(url).content.decode("latin-1")
        f.write_text(text, encoding="latin-1")
        return text

    def activist_filings(self, ciks: list[str], days: int = 60) -> list[dict]:
        """Recent 13D filings by the given filer CIKs (the SEC's submissions API)."""
        from datetime import date, timedelta
        since = (date.today() - timedelta(days=days)).isoformat()
        out = []
        for cik in ciks:
            data = self._get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json").json()
            out += parse_submissions(data, since)
        return sorted(out, key=lambda e: e["filed"], reverse=True)
