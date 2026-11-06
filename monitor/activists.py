"""Decide whether a filing was made by a known activist, by matching the filer's name."""
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "data" / "activists.txt"


def load_patterns(path: Path = DEFAULT) -> list[str]:
    return [l.strip().lower() for l in Path(path).read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def match_activist(filer_names: list[str], patterns: list[str] | None = None) -> str | None:
    """Return the first matching pattern (a stable activist key), or None."""
    patterns = load_patterns() if patterns is None else patterns
    for name in filer_names:
        n = name.lower()
        for p in patterns:
            if p in n:
                return p
    return None
