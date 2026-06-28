"""
Governance layer — every signal passes through this before reaching the DB or API.
Import and call validate_signal() at the end of impact_reasoner.py.
Call validate_backtest() in scripts/backtest.py before returning results.
"""

import re
from dataclasses import dataclass
from typing import Optional

# ── Constants — do not make these configurable ─────────────────────────────

MIN_CONFIDENCE         = 0.65    # below this → signal discarded
MIN_SOURCE_TIER        = 2       # tier 1 (blogs) → signal flagged only
MIN_CORROBORATING      = 2       # single-source alerts are suppressed
MAX_BACKTEST_DAYS      = 5       # look-ahead window hard cap
MIN_BACKTEST_SAMPLE    = 30      # accuracy hidden below this
HIGH_CONFIDENCE_FLAG   = 0.85    # above this → flag for human review

DISCLAIMER = (
    "NOT FINANCIAL ADVICE. This is an educational analysis only. "
    "Past patterns do not guarantee future results. "
    "Do not make investment decisions based on this output."
)

BACKTEST_DISCLAIMER = (
    "BACKTESTING NOTICE: Historical correlation between signals and price moves "
    "does not predict future performance. This is an evaluation tool only. "
    "Do not use backtest results to make investment decisions."
)

PROHIBITED_PHRASES = [
    "buy",  "sell",  "invest",  "purchase",
    "go short",  "short the",  "short position",  "short selling",
    "guaranteed",  "will increase",  "will decrease",
    "price target",  "strong buy",  "strong sell",
    "recommend",  "should buy",  "should sell",
    "going to rise",  "going to fall",  "sure bet",
]

REQUIRED_SIGNAL_FIELDS = [
    "event_type", "sentiment", "confidence",
    "impact_summary", "source_citations",
    "uncertainty_factors", "disclaimer",
]

SOURCE_TIERS = {
    # Tier 3 — wire services (highest credibility)
    "reuters":    3, "associated press": 3, "ap news": 3,
    "bloomberg":  3, "dow jones": 3,
    # Tier 2 — major outlets
    "cnbc":       2, "wall street journal": 2, "wsj": 2,
    "financial times": 2, "ft": 2, "marketwatch": 2,
    "seeking alpha": 2, "barron's": 2, "yahoo finance": 2,
    # Tier 1 — blogs, unknown (lowest credibility)
    "default":    1,
}


@dataclass
class GovernanceResult:
    passed:           bool
    signal:           Optional[dict]
    rejection_reason: Optional[str]
    warnings:         list[str]


def get_source_tier(source: str) -> int:
    source_lower = source.lower()
    for name, tier in SOURCE_TIERS.items():
        if name in source_lower:
            return tier
    return SOURCE_TIERS["default"]


def contains_prohibited_phrase(text: str) -> Optional[str]:
    """Returns the first prohibited phrase found, or None."""
    text_lower = text.lower()
    for phrase in PROHIBITED_PHRASES:
        if re.search(r'\b' + re.escape(phrase) + r'\b', text_lower):
            return phrase
    return None


def validate_signal(raw_signal: dict, sources: list[str]) -> GovernanceResult:
    """
    Main governance gate. Call this on every impact_reasoner output.

    Args:
        raw_signal: The JSON dict produced by the impact reasoner
        sources:    List of source names for this article/signal

    Returns:
        GovernanceResult with passed=True if signal should be stored/displayed
    """
    warnings = []

    # ── 1. Check for no_signal from reasoner ─────────────────────────────
    if raw_signal.get("signal") == "no_signal":
        return GovernanceResult(
            passed=False,
            signal=None,
            rejection_reason=f"Reasoner returned no_signal: {raw_signal.get('reason')}",
            warnings=[]
        )

    # ── 2. Required fields ────────────────────────────────────────────────
    for field in REQUIRED_SIGNAL_FIELDS:
        if field not in raw_signal or raw_signal[field] is None:
            return GovernanceResult(
                passed=False,
                signal=None,
                rejection_reason=f"Missing required field: {field}",
                warnings=[]
            )

    # ── 3. Confidence threshold ───────────────────────────────────────────
    confidence = float(raw_signal.get("confidence", 0))
    if confidence < MIN_CONFIDENCE:
        return GovernanceResult(
            passed=False,
            signal=None,
            rejection_reason=f"Confidence {confidence:.2f} below minimum {MIN_CONFIDENCE}",
            warnings=[]
        )

    # ── 4. Prohibited phrases in impact_summary ───────────────────────────
    bad_phrase = contains_prohibited_phrase(
        raw_signal.get("impact_summary", "") +
        raw_signal.get("reasoning", "")
    )
    if bad_phrase:
        return GovernanceResult(
            passed=False,
            signal=None,
            rejection_reason=f"Prohibited phrase found: '{bad_phrase}'",
            warnings=[]
        )

    # ── 5. Source credibility ─────────────────────────────────────────────
    source_tiers = [get_source_tier(s) for s in sources]
    max_tier     = max(source_tiers) if source_tiers else 1

    if max_tier < MIN_SOURCE_TIER:
        warnings.append(
            f"Low source credibility (tier {max_tier}). "
            "Signal shown with warning. Verify independently."
        )

    # ── 6. Corroboration check ────────────────────────────────────────────
    if len(sources) < MIN_CORROBORATING:
        warnings.append(
            f"Only {len(sources)} source(s). "
            f"Alert suppressed until {MIN_CORROBORATING}+ sources corroborate."
        )
        raw_signal["alert_suppressed"] = True
        raw_signal["alert_suppressed_reason"] = "Insufficient corroborating sources"

    # ── 7. High-confidence human review flag ─────────────────────────────
    if confidence >= HIGH_CONFIDENCE_FLAG:
        warnings.append(
            f"High confidence signal ({confidence:.2f}). "
            "Flagged for human review before acting on."
        )
        raw_signal["requires_human_review"] = True

    # ── 8. Enforce disclaimer (overwrite whatever reasoner produced) ──────
    raw_signal["disclaimer"]              = DISCLAIMER
    raw_signal["governance_passed"]       = True
    raw_signal["source_credibility_tier"] = max_tier
    raw_signal["governance_warnings"]     = warnings

    return GovernanceResult(
        passed=True,
        signal=raw_signal,
        rejection_reason=None,
        warnings=warnings
    )


# ── Backtesting governance ─────────────────────────────────────────────────

@dataclass
class BacktestGovernanceResult:
    result:   dict
    warnings: list[str]


def validate_backtest(raw_result: dict) -> BacktestGovernanceResult:
    """
    Apply governance rules to every backtest result before display.
    Called in scripts/backtest.py before returning any result to the API.
    """
    warnings = []

    # ── 1. Hard cap on look-ahead window ─────────────────────────────────
    look_ahead = raw_result.get("look_ahead_days", 0)
    if look_ahead > MAX_BACKTEST_DAYS:
        raw_result["look_ahead_days"] = MAX_BACKTEST_DAYS
        warnings.append(
            f"Look-ahead window capped at {MAX_BACKTEST_DAYS} days "
            f"(was {look_ahead}). Longer windows reflect noise, not the event."
        )

    # ── 2. Minimum sample size ────────────────────────────────────────────
    sample_size = raw_result.get("sample_size", 0)
    if sample_size < MIN_BACKTEST_SAMPLE:
        raw_result["accuracy"]      = None
        raw_result["accuracy_note"] = (
            f"Accuracy hidden: only {sample_size} events "
            f"(need {MIN_BACKTEST_SAMPLE}+). Collect more data."
        )
        warnings.append(raw_result["accuracy_note"])

    # ── 3. Always show coin-flip baseline ────────────────────────────────
    raw_result["baseline_accuracy"] = 0.50
    if raw_result.get("accuracy") is not None:
        raw_result["vs_baseline"] = round(
            raw_result["accuracy"] - 0.50, 4
        )
        if raw_result["accuracy"] > 0.80:
            warnings.append(
                "Accuracy above 80% is suspicious — check for data leakage. "
                "Ensure news publish_date precedes the price move date."
            )

    # ── 4. Always attach disclaimer ───────────────────────────────────────
    raw_result["disclaimer"]        = BACKTEST_DISCLAIMER
    raw_result["governance_warnings"] = warnings

    return BacktestGovernanceResult(result=raw_result, warnings=warnings)
