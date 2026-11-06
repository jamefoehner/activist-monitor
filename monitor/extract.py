"""Pure parsing functions: pull the Item 4 "Purpose of Transaction" text out of a 13D filing.

Adapted from the activist-target-screener project (extract_item4.py). No network, no pandas.
"""
import html
import re

FORMS_13D = ("SC 13D", "SCHEDULE 13D")
MAX_CHARS = 60_000

START_STRICT = re.compile(
    r"item\s*4\s*[\.\:\-–—]?\s*(?:\(\w\)\s*)?purpose\s+of\s+(?:the\s+)?transactions?", re.I)
END_STRICT = re.compile(
    r"item\s*5\s*[\.\:\-–—]?\s*(?:\(\w\)\s*)?interests?\s+in\s+(?:the\s+)?securities", re.I)
START_LOOSE = re.compile(r"\bitem\s*4\b", re.I)
END_LOOSE = re.compile(r"\bitem\s*5\b", re.I)


def primary_document(raw: str) -> tuple[str, str]:
    """Return (document type, body) of the 13D itself, not its exhibits."""
    docs = re.split(r"<DOCUMENT>", raw, flags=re.I)[1:]
    parsed = []
    for d in docs:
        t = re.search(r"<TYPE>\s*([^\n<]+)", d, re.I)
        body = re.search(r"<TEXT>(.*?)</TEXT>", d, re.I | re.S)
        parsed.append(((t.group(1).strip() if t else ""), body.group(1) if body else d))
    for typ, body in parsed:
        if typ.upper().startswith(FORMS_13D):
            return typ, body
    return parsed[0] if parsed else ("", raw)


def html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def from_xml(body: str):
    """Structured filings (Dec 2024+): find an element whose name mentions 'purpose'."""
    hits = re.findall(r"<([\w:]*purpose\w*)[^>]*>(.*?)</\1>", body, re.I | re.S)
    texts = [html_to_text(h[1]) for h in hits if len(html_to_text(h[1])) > 20]
    return max(texts, key=len) if texts else None


def best_section(text: str, start_re, end_re):
    """Longest span from a start heading to the next end heading. Picking the longest
    skips cross-references like 'as described in Item 4' that appear earlier."""
    best = None
    for m in start_re.finditer(text):
        e = end_re.search(text, m.end())
        if not e:
            continue
        span = text[m.end():e.start()].strip(" .:-\n")
        if best is None or len(span) > len(best):
            best = span
    return best


def extract_item4(raw: str) -> tuple[str | None, str]:
    """Return (item4_text or None, how it was found)."""
    typ, body = primary_document(raw)
    if "<?xml" in body[:500].lower() or re.search(r"<\w*schedule13d", body[:5000], re.I):
        t = from_xml(body)
        if t:
            return t[:MAX_CHARS], "xml_element"
        # A structured filing with no Item 4 element does not amend Item 4. Do NOT fall back to text
        # heading search: it can latch onto an "Item 4" mention and return another item's text.
        return None, "xml_no_item4"
    text = html_to_text(body) if re.search(r"<(html|body|p|div|table)\b", body, re.I) else body
    text = re.sub(r"[ \t]+", " ", text)
    for start_re, end_re, how in [(START_STRICT, END_STRICT, "heading_strict"),
                                  (START_LOOSE, END_LOOSE, "heading_loose")]:
        sec = best_section(text, start_re, end_re)
        if sec and len(sec) >= 40:
            return sec[:MAX_CHARS], how
    return None, "not_found"


def parse_header(raw: str) -> dict:
    """Names from the SGML header: {'subject': str | None, 'filers': [str, ...]}.

    The header has one 'SUBJECT COMPANY:' block and one or more 'FILED BY:' blocks,
    each containing 'COMPANY CONFORMED NAME:'.
    """
    head = raw.split("</SEC-HEADER>", 1)[0]
    parts = re.split(r"^(SUBJECT COMPANY:|FILED BY:)\s*$", head, flags=re.M)
    subject, filers = None, []
    # parts = [preamble, marker1, body1, marker2, body2, ...]
    for marker, body in zip(parts[1::2], parts[2::2]):
        m = re.search(r"COMPANY CONFORMED NAME:\s*(.+)", body)
        if not m:
            continue
        name = m.group(1).strip()
        if marker.startswith("SUBJECT"):
            subject = subject or name
        else:
            filers.append(name)
    return {"subject": subject, "filers": filers}
