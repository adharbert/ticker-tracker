# Governance — Rules, Guardrails & Disclaimers

> Claude Code: build `python-agent/governance/guardrails.py` from this spec.
> These rules are STRUCTURAL — enforced in code, not just documentation.
> Every signal output passes through the governance gate before storage or display.
> No exceptions. No configuration flags to disable them.

---

## Why governance is in code, not docs

A README saying "don't use this for trading" doesn't protect you from bad decisions
made at 2am when a signal looks very convincing. Code that physically cannot emit a
buy/sell recommendation, cannot exceed a confidence threshold without flagging, and
always attaches a disclaimer — does.

This is also a learning objective: understanding how to build responsible AI systems
is as important as understanding how to build capable ones.

---

## File: `python-agent/governance/guardrails.py`

```python
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
    "buy",  "sell",  "invest",  "purchase",  "short",
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
    passed:        bool
    signal:        Optional[dict]
    rejection_reason: Optional[str]
    warnings:      list[str]


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
        # Still store the signal, but flag as not-alertable
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
    raw_result["disclaimer"] = BACKTEST_DISCLAIMER
    raw_result["governance_warnings"] = warnings

    return BacktestGovernanceResult(result=raw_result, warnings=warnings)
```

---

## Governance in the C# API

The .NET API enforces a second layer of governance on the signal response shape.
In `SignalsController.cs`, always run this check before returning to React:

```csharp
private bool SignalPassesGovernance(Signal signal)
{
    // Reject signals the Python layer should have caught
    if (string.IsNullOrEmpty(signal.Disclaimer)) return false;
    if (!signal.GovernancePassed) return false;
    if (signal.Confidence < 0.65m) return false;

    // Double-check prohibited phrases in impact summary
    var prohibited = new[] { "buy", "sell", "invest", "guaranteed", "price target" };
    return !prohibited.Any(p =>
        signal.ImpactSummary?.Contains(p, StringComparison.OrdinalIgnoreCase) ?? false);
}
```

---

## Governance in the React UI

The `GovernanceBadge` component is rendered on **every** signal card and **every**
backtest result page. It cannot be hidden, toggled off, or styled as secondary content.

```jsx
// components/GovernanceBadge.jsx
// REQUIRED on every SignalCard and BacktestPage
// Do not make this dismissible or collapsible

export default function GovernanceBadge({ compact = false }) {
  if (compact) {
    return (
      <span style={{
        display: "inline-block",
        padding: "2px 8px",
        background: "#fee2e2",
        color: "#991b1b",
        borderRadius: 4,
        fontSize: "0.7rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
      }}>
        NOT FINANCIAL ADVICE
      </span>
    );
  }

  return (
    <div style={{
      padding: "0.5rem 0.75rem",
      background: "#fee2e2",
      border: "1px solid #fecaca",
      borderRadius: 6,
      fontSize: "0.8rem",
      color: "#7f1d1d",
      lineHeight: 1.5,
    }}>
      <strong>Educational analysis only.</strong> This output is generated by AI
      and may be incorrect. Past correlations do not predict future price movements.
      Do not make investment decisions based on this content.
    </div>
  );
}
```

---

## Backtesting governance UI rules

When displaying backtest results in `BacktestPage.jsx`:

1. Always show `baseline_accuracy` (50%) alongside model accuracy
2. Label the comparison: "Your signals: 58% | Coin flip: 50% | Edge: +8%"
3. Show `accuracy_note` if accuracy is null (insufficient data)
4. Show all `governance_warnings` as yellow info boxes
5. The page title must read "Signal Evaluation (Backtesting)" — not "Predictions"
6. Add a static callout at the top: "This page measures how well past signals
   correlated with actual price moves. It does not predict future movements."

---

## What is structurally impossible

These things cannot happen because of how the code is wired, not because of policy:

- A signal with `confidence < 0.65` reaches the database
- A signal with "buy" or "sell" in its text reaches the database
- A signal is displayed without a disclaimer
- A backtest result shows accuracy without the baseline comparison
- A backtest uses a look-ahead window > 5 days
- The system connects to any brokerage or trading API (no such code exists)
- An alert fires without 2+ corroborating sources
