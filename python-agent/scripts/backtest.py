"""
backtest.py — Correlate historical signals with actual price moves.

For each governance-passed signal, looks up the closing price on the signal date
and N days later, then checks whether the signal direction (bullish/bearish) matched
the actual price move. Stores per-ticker results in backtest_results table.

Run manually: python -m scripts.backtest
Governance rules applied: look-ahead capped at 5 days, accuracy hidden if < 30 samples.
"""

import os, logging
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

import psycopg2
from psycopg2.extras import RealDictCursor
from governance.guardrails import validate_backtest

DB_CONN         = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost:5433/news_market")
LOOK_AHEAD_DAYS = int(os.getenv("BACKTEST_LOOK_AHEAD", "5"))


def _get_price(cur, ticker: str, target_date: date, tolerance_days: int = 3,
               forward_only: bool = False) -> float | None:
    """
    Return the closing price for ticker on target_date.
    If no exact match, use the nearest trading day within tolerance_days.
    forward_only restricts the window to [target_date, target_date + tolerance_days] —
    used for the look-ahead exit price so a too-recent signal whose outcome window
    hasn't elapsed yet can't be graded against an earlier substitute price.
    Returns None if no price found within tolerance.
    """
    lower = target_date if forward_only else target_date - timedelta(days=tolerance_days)
    cur.execute("""
        SELECT close FROM prices
        WHERE ticker = %s
          AND date BETWEEN %s AND %s
          AND close IS NOT NULL
        ORDER BY ABS(date - %s)
        LIMIT 1
    """, (ticker, lower, target_date + timedelta(days=tolerance_days), target_date))
    row = cur.fetchone()
    return float(row["close"]) if row else None


def _direction(bullish_or_bearish: str) -> int:
    """Convert sentiment to expected direction: +1 bullish, -1 bearish, 0 neutral."""
    s = (bullish_or_bearish or "").lower()
    if s == "bullish":
        return 1
    if s == "bearish":
        return -1
    return 0


def run_backtest(look_ahead_days: int = LOOK_AHEAD_DAYS) -> list[dict]:
    """
    Compute backtest results for every ticker that has governance-passed signals.
    Returns list of result dicts (one per ticker+event_type combination).
    """
    look_ahead_days = min(look_ahead_days, 5)  # governance cap enforced here too
    conn = psycopg2.connect(DB_CONN)
    results = []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Anchor on the article's actual publication date, not signals.published_at
            # (which is stamped at pipeline-run time and can lag the real news by weeks —
            # see docs/PHASES.md Phase 3 notes). Falls back to signal date if no article match.
            cur.execute("""
                SELECT s.id, s.ticker, s.sentiment, s.event_type,
                       COALESCE(n.published_at::date, s.published_at::date) AS signal_date
                FROM signals s
                LEFT JOIN news_articles n ON n.id = s.article_id
                WHERE s.governance_passed = TRUE
                ORDER BY s.ticker, signal_date
            """)
            signals = cur.fetchall()

        log.info(f"Backtesting {len(signals)} signals with {look_ahead_days}-day look-ahead")

        # Group by ticker
        by_ticker: dict[str, list] = {}
        for s in signals:
            by_ticker.setdefault(s["ticker"], []).append(s)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for ticker, ticker_signals in by_ticker.items():
                evaluated = []

                for sig in ticker_signals:
                    signal_date  = sig["signal_date"]
                    future_date  = signal_date + timedelta(days=look_ahead_days)

                    price_entry = _get_price(cur, ticker, signal_date)
                    price_exit  = _get_price(cur, ticker, future_date, forward_only=True)

                    if price_entry is None or price_exit is None:
                        log.debug(f"No price data for {ticker} around {signal_date} — skipping")
                        continue

                    price_change = price_exit - price_entry
                    actual_dir   = 1 if price_change > 0 else (-1 if price_change < 0 else 0)
                    signal_dir   = _direction(sig["sentiment"])

                    if signal_dir == 0:
                        continue  # neutral signals not counted

                    correct = (signal_dir == actual_dir)
                    evaluated.append({
                        "signal_id":    str(sig["id"]),
                        "signal_date":  signal_date.isoformat(),
                        "sentiment":    sig["sentiment"],
                        "event_type":   sig["event_type"],
                        "price_entry":  price_entry,
                        "price_exit":   price_exit,
                        "price_change": round(price_change, 4),
                        "correct":      correct,
                    })

                sample_size = len(evaluated)

                if sample_size == 0:
                    log.info(f"{ticker}: no evaluable signals (missing price data or all-neutral)")

                raw = {
                    "ticker":           ticker,
                    "event_type":       None,
                    "look_ahead_days":  look_ahead_days,
                    "sample_size":      sample_size,
                    "accuracy":         round(sum(1 for e in evaluated if e["correct"]) / sample_size, 4) if sample_size else None,
                    "accuracy_note":    None,  # validate_backtest() fills this in for sample_size < 30
                    "baseline_accuracy": 0.50,
                    "vs_baseline":      None,
                }

                governed = validate_backtest(raw)
                result   = governed.result
                results.append(result)

                log.info(
                    f"{ticker}: {sample_size} signals evaluated, "
                    f"accuracy={result.get('accuracy')} "
                    f"vs_baseline={result.get('vs_baseline')}"
                )

                # Persist to DB
                with conn.cursor() as wcur:
                    wcur.execute("DELETE FROM backtest_results WHERE ticker = %s", (ticker,))
                    wcur.execute("""
                        INSERT INTO backtest_results
                            (ticker, event_type, look_ahead_days, sample_size,
                             accuracy, accuracy_note, baseline_accuracy, vs_baseline,
                             disclaimer)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        result["ticker"],
                        result.get("event_type"),
                        result["look_ahead_days"],
                        result["sample_size"],
                        result.get("accuracy"),
                        result.get("accuracy_note"),
                        result["baseline_accuracy"],
                        result.get("vs_baseline"),
                        result["disclaimer"],
                    ))
                conn.commit()

    finally:
        conn.close()

    log.info(f"Backtest complete: {len(results)} tickers evaluated")
    return results


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else LOOK_AHEAD_DAYS
    results = run_backtest(days)
    for r in results:
        acc = f"{r['accuracy']:.1%}" if r.get("accuracy") is not None else "hidden (<30 samples)"
        print(f"  {r['ticker']:8s}  samples={r['sample_size']:3d}  accuracy={acc}  vs_baseline={r.get('vs_baseline')}")
