import os, logging

log = logging.getLogger(__name__)

EVENT_KEYWORDS = {
    "fed_rate":   ["federal reserve", "fed", "rate hike", "rate cut", "fomc",
                   "interest rate", "powell", "basis points", "bps", "monetary policy"],
    "earnings":   ["earnings", "eps", "revenue", "beats", "misses", "guidance",
                   "quarterly", "q1", "q2", "q3", "q4", "annual results", "profit"],
    "merger":     ["merger", "acquisition", "takeover", "buyout", "deal",
                   "acquired", "acquires", "merge", "tender offer"],
    "regulatory": ["sec", "ftc", "doj", "antitrust", "fine", "penalty",
                   "investigation", "subpoena", "regulation", "compliance", "lawsuit"],
    "macro":      ["cpi", "inflation", "gdp", "unemployment", "jobs report",
                   "nonfarm", "pce", "treasury", "yield", "recession", "debt ceiling"],
}


def classify_event(headline: str, body: str = "") -> tuple[str, float]:
    """
    Phase 1: keyword-based classifier. Fast, no GPU, no Ollama required.
    Returns (event_type, confidence). event_type='noise' means skip this article.
    Phase 2 upgrade: replace with classify_event_llm() from docs/AGENTS.md.
    """
    text   = (headline + " " + body).lower()
    scores = {}

    for event_type, keywords in EVENT_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            scores[event_type] = matches / len(keywords)

    if not scores:
        return "noise", 0.0

    best = max(scores, key=scores.get)
    if scores[best] < 0.05:
        return "noise", scores[best]

    return best, min(scores[best] * 10, 1.0)
