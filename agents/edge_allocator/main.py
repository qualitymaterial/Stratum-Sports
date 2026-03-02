import json
import logging
import os
from datetime import date
from urllib import error, request

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

from allocator import build_allocation_report
from discord_formatter import format_discord_summary
from query_builder import QueryBuilder


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_local_env() -> None:
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    local_env = os.path.join(agent_dir, ".env")
    if os.path.exists(local_env):
        load_dotenv(local_env)


def _normalize_conn_str(db_url: str) -> str:
    conn_str = db_url
    if "://" in conn_str:
        prefix, rest = conn_str.split("://", 1)
        if "postgres" in prefix:
            conn_str = "postgres://" + rest
    return conn_str


def fetch_segment_rows(db_url: str) -> list[dict]:
    query = QueryBuilder.build_segment_metrics_query()
    conn_str = _normalize_conn_str(db_url)
    rows: list[dict] = []

    with psycopg2.connect(conn_str) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query)
            rows = [dict(row) for row in cur.fetchall()]
    return rows


def post_to_discord(webhook_url: str, content: str) -> None:
    payload = json.dumps({"content": content}).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=10):
            return
    except error.URLError as exc:
        logger.error("Discord post failed: %s", exc)


def main() -> None:
    _load_local_env()
    db_url = os.getenv("DATABASE_URL")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")

    if not db_url:
        logger.error("Missing DATABASE_URL")
        return

    try:
        rows = fetch_segment_rows(db_url)
    except Exception as exc:
        logger.error("Query execution failed: %s", exc)
        return

    report_date = date.today().isoformat()
    report = build_allocation_report(rows, report_date)

    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)

    file_name = f"edge_allocation_{report_date}.json"
    file_path = os.path.join(out_dir, file_name)
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    logger.info("Edge allocation report saved to %s", file_path)

    summary = format_discord_summary(report)
    if discord_webhook:
        post_to_discord(discord_webhook, summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
