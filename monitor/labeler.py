"""Label Item 4 text with ten demand categories using the Claude API.

The prompt is the condensed labeling guide from the activist-target-screener RL study.
Set ANTHROPIC_API_KEY. Model defaults to MONITOR_MODEL or claude-sonnet-5-5.
"""
import json
import os
import re

FIELDS = ["board_seats", "sale_or_review", "breakup_spin", "capital_return", "operations_costs",
          "management_change", "governance", "oppose_deal", "capital_discipline", "engagement_only"]

GUIDE = """You label SEC Schedule 13D Item 4 text from activist investors.
Label what the activist says it INTENDS, SEEKS or RECOMMENDS for this company. Ignore boilerplate
("may engage in discussions", "may take actions relating to clauses (a)-(j)") and mere reservations of rights.
Fields (1 = yes, 0 = no):
- board_seats: nominating directors / seeking board representation / settlement adding directors
- sale_or_review: sale of the company, merger, strategic review or alternatives
- breakup_spin: spin-off, separation, or sale of a division
- capital_return: buybacks, special dividends, returning cash
- operations_costs: cost cuts, margin improvement, operational restructuring
- management_change: replacing the CEO or executives
- governance: declassify board, remove poison pill, bylaw/charter changes, shareholder rights
- oppose_deal: opposing an announced merger/acquisition or demanding better terms
- capital_discipline: limit acquisitions/capex, improve returns on capital, reduce debt, capital allocation policy
- engagement_only: none of the above, only 'investment purposes' and discussions with management.
  Never 1 together with another field.
Also return "not_a_demand": 1 ONLY when every field above is 0 and the text is purely administrative or
about the filer's own holdings, such as selling shares, an in-kind distribution, a trust or plan
reporting its holdings, or a change in ownership percentage, with no stated plans for the company.
Otherwise 0.
Reply with ONLY a JSON object with exactly these keys: """ + ", ".join(FIELDS) + ", not_a_demand."

MAX_INPUT_CHARS = 30_000
MAX_REPLY_TOKENS = 1000  # 200 cut off replies that began with reasoning, before the JSON


def parse_answer(s: str):
    """Return dict of 0/1 for all FIELDS, or None if unparseable or inconsistent."""
    # The model sometimes reasons in prose first. Take the last {...} block that is a valid answer.
    out = None
    for m in reversed(list(re.finditer(r"\{[^{}]*\}", s))):
        try:
            d = json.loads(m.group(0))
            out = {f: int(bool(int(d[f]))) for f in FIELDS}
            break
        except Exception:
            continue
    if out is None:
        return None
    if out["engagement_only"] and any(out[f] for f in FIELDS if f != "engagement_only"):
        return None  # the guide forbids this combination; treat as a failed parse
    try:  # extension for the app, not part of the validated ten-field research prompt
        out["not_a_demand"] = int(bool(int(d.get("not_a_demand", 0))))
    except Exception:
        out["not_a_demand"] = 0
    if out["not_a_demand"] and any(out[f] for f in FIELDS):
        return None
    return out


class Labeler:
    def __init__(self, client=None, model: str | None = None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("MONITOR_MODEL", "claude-sonnet-5-5")

    def label(self, item4_text: str, retries: int = 1):
        """Return (labels dict or None, raw model reply)."""
        raw = ""
        for _ in range(retries + 1):
            msg = self.client.messages.create(
                model=self.model, max_tokens=MAX_REPLY_TOKENS, system=GUIDE,
                messages=[{"role": "user",
                           "content": f"Item 4 text:\n\n{item4_text[:MAX_INPUT_CHARS]}\n\nJSON:"}])
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            parsed = parse_answer(raw)
            if parsed is not None:
                return parsed, raw
        return None, raw
