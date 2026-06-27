import os, logging
import yfinance as yf
import psycopg2
from datetime import datetime, timedelta

log = logging.getLogger(__name__)
DB_CONN = os.getenv("DB_CONNECTION", "postgresql://postgres:postgres@localhost/news_market")


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
                            float(row["Open"].iloc[0]) if hasattr(row["Open"], "iloc") else float(row["Open"]),
                            float(row["High"].iloc[0]) if hasattr(row["High"], "iloc") else float(row["High"]),
                            float(row["Low"].iloc[0])  if hasattr(row["Low"],  "iloc") else float(row["Low"]),
                            float(row["Close"].iloc[0]) if hasattr(row["Close"], "iloc") else float(row["Close"]),
                            int(row["Volume"].iloc[0])  if hasattr(row["Volume"], "iloc") else int(row["Volume"]),
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
