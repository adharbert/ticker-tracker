import os, logging, math
import yfinance as yf
import psycopg2
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/news_market")


def _f(val) -> float | None:
    """Extract float from a pandas scalar or Series iloc[0]; return None for NaN/Inf."""
    if hasattr(val, "iloc"):
        val = val.iloc[0]
    try:
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def _i(val) -> int | None:
    """Extract int from a pandas scalar or Series iloc[0]; return None for NaN."""
    f = _f(val)
    return None if f is None else int(f)


def fetch_prices(tickers: list[str] = None, days_back: int = 30) -> dict:
    """Fetch daily OHLCV for each ticker and upsert into prices table."""
    conn  = psycopg2.connect(DB_CONN)
    end   = datetime.today()
    start = end - timedelta(days=days_back)

    if tickers is None:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker FROM watchlist ORDER BY ticker")
            tickers = [row[0] for row in cur.fetchall()]

    stats = {"tickers": len(tickers), "rows": 0, "errors": []}

    for ticker in tickers:
        try:
            df = yf.download(ticker, start=start, end=end,
                             progress=False, auto_adjust=True)
            if df.empty:
                log.warning(f"No price data returned for {ticker}")
                continue

            df.reset_index(inplace=True)
            # Flatten multi-level columns from newer yfinance versions
            if isinstance(df.columns, type(df.columns)) and hasattr(df.columns, 'levels'):
                df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

            with conn:
                with conn.cursor() as cur:
                    for _, row in df.iterrows():
                        cur.execute("""
                            INSERT INTO prices
                                (ticker, date, open, high, low, close, volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ticker, date) DO UPDATE
                            SET open   = EXCLUDED.open,
                                high   = EXCLUDED.high,
                                low    = EXCLUDED.low,
                                close  = EXCLUDED.close,
                                volume = EXCLUDED.volume
                        """, (
                            ticker,
                            row["Date"].date() if hasattr(row["Date"], "date") else row["Date"],
                            _f(row["Open"]),
                            _f(row["High"]),
                            _f(row["Low"]),
                            _f(row["Close"]),
                            _i(row["Volume"]),
                        ))
                        stats["rows"] += 1

            log.info(f"Prices fetched for {ticker}: {len(df)} days")

        except Exception as e:
            log.error(f"Failed to fetch prices for {ticker}: {e}")
            stats["errors"].append({"ticker": ticker, "error": str(e)})

    conn.close()
    return stats


if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    result = fetch_prices()
    print(f"Price fetch complete: {result}")
