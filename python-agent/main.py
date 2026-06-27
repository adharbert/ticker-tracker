import os, logging, threading
from dotenv import load_dotenv
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
log = logging.getLogger(__name__)

PORT          = int(os.getenv("PYTHON_AGENT_PORT", "5001"))
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "07:00")

app = Flask(__name__)
_pipeline_lock = threading.Lock()


def run_pipeline() -> dict:
    """
    Phase 1: fetch news + prices, classify events, store in DB + ChromaDB.
    Phase 2: add sentiment + impact reasoning (swap fetch_and_store_all
             for the full pipeline in agents/news_fetcher.py).
    """
    if not _pipeline_lock.acquire(blocking=False):
        log.info("Pipeline already running — skipping")
        return {"status": "already_running"}

    try:
        from agents.news_fetcher  import fetch_and_store_all
        from agents.price_fetcher import fetch_prices

        log.info("Starting news fetch...")
        news_result  = fetch_and_store_all()

        log.info("Starting price fetch...")
        price_result = fetch_prices()

        result = {
            "status":       "ok",
            "news":         news_result,
            "prices":       price_result,
        }
        log.info(f"Pipeline complete: {result}")
        return result

    except Exception as e:
        log.error(f"Pipeline failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        _pipeline_lock.release()


@app.route("/trigger", methods=["POST"])
def trigger():
    """Called by C# IngestController for manual ingest."""
    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return jsonify({"status": "triggered"}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "port": PORT}), 200


@app.route("/stats", methods=["GET"])
def stats():
    try:
        from rag.chroma_store import get_stats
        chroma = get_stats()
    except Exception:
        chroma = {"error": "ChromaDB unavailable"}
    return jsonify({"chroma": chroma}), 200


def start_scheduler():
    hour, minute = SCHEDULE_TIME.split(":")
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_pipeline,
        trigger="cron",
        day_of_week="mon-fri",
        hour=int(hour),
        minute=int(minute),
        id="daily_ingest",
    )
    scheduler.start()
    log.info(f"Scheduler running — daily ingest at {SCHEDULE_TIME} (Mon-Fri)")
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()

    log.info(f"Python agent starting on port {PORT}")
    log.info(f"Manual trigger: POST http://localhost:{PORT}/trigger")
    log.info(f"Health check:   GET  http://localhost:{PORT}/health")

    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
