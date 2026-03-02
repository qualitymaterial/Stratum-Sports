import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI
import requests

from schema_inspector import SchemaInspector
from query_builder import QueryBuilder
from metrics import MetricsProcessor

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def execute_queries(db_url, queries):
    results = {}
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for name, sql in queries.items():
                logger.info(f"Executing {name}...")
                cur.execute(sql)
                results[name] = cur.fetchall()
        conn.close()
    except Exception as e:
        # Check if database hostname needs translation (e.g. localhost -> db)
        logger.error(f"Execution failed: {e}")
    return results

def post_to_discord(webhook_url, final_report):
    if not webhook_url:
        return
    
    summary = final_report["summary"]
    interpretation = final_report.get("interpretation", "No interpretation available.")
    
    # Identify degrading or high risk signals
    critical = [s["signal_type"] for s in final_report["signals"] if s["classification"] == "degrading" or s["risk_level"] == "high"]
    critical_str = "\n".join([f"- {s}" for s in critical]) if critical else "None"

    content = f"""**Signal Quality Audit: {final_report['date']}**

**Summary:**
- Total Types: {summary['total_signal_types']}
- Degrading: {summary['degrading_count']}
- Improving: {summary['improving_count']}
- Stable: {summary['stable_count']}

**Critical Signals (High Risk/Degrading):**
{critical_str}

**Interpretation:**
> {interpretation}
"""
    try:
        requests.post(webhook_url, json={"content": content})
    except Exception as e:
        logger.error(f"Discord post failed: {e}")

def main():
    # 1. Config
    db_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")

    if not db_url or not api_key:
        logger.error("Missing DATABASE_URL or OPENAI_API_KEY")
        return

    # 2. Introspect
    inspector = SchemaInspector(db_url)
    schema_map = inspector.inspect()
    
    # 3. Query
    builder = QueryBuilder(schema_map)
    queries = builder.build_queries()
    raw_results = execute_queries(db_url, queries)
    
    # 4. Deterministic Processing
    processor = MetricsProcessor(raw_results)
    audit_results = processor.process()
    
    # 5. LLM Interpretation
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    with open(prompt_path, "r") as f:
        prompt_tmpl = f.read()
    
    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_tmpl.format(data=json.dumps(audit_results, default=str))},
                {"role": "user", "content": "Analyze the signal quality data and provide optimizations."}
            ],
            response_format={"type": "json_object"}
        )
        llm_output = json.loads(response.choices[0].message.content)
        audit_results.update(llm_output)
    except Exception as e:
        logger.error(f"LLM Interpretation failed: {e}")

    # 6. Save Output
    audit_results["date"] = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    
    filename = f"quality_report_{audit_results['date']}.json"
    file_path = os.path.join(out_dir, filename)
    with open(file_path, "w") as f:
        json.dump(audit_results, f, indent=2)
    
    logger.info(f"Audit saved to {file_path}")

    # 7. Discord
    post_to_discord(discord_webhook, audit_results)

if __name__ == "__main__":
    main()
