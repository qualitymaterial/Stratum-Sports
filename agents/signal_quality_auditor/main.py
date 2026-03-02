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
# Load local .env first
agent_dir = os.path.dirname(os.path.abspath(__file__))
local_env = os.path.join(agent_dir, ".env")
if os.path.exists(local_env):
    load_dotenv(local_env)
# Do not call load_dotenv() without arguments to avoid permission errors on /repo/.env
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def execute_queries(db_url, queries):
    results = {}
    # Psycopg2 prefers postgres:// and doesn't support +driver prefixes
    conn_str = db_url
    if "://" in conn_str:
        prefix, rest = conn_str.split("://", 1)
        if "postgres" in prefix:
            conn_str = "postgres://" + rest
        
    try:
        conn = psycopg2.connect(conn_str)
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
    interpretation = final_report.get("executive_interpretation", "No interpretation available.")
    
    # Identify degrading or high-risk segments
    critical: list[str] = []
    for sig in final_report.get("signals", []):
        signal_type = sig.get("signal_type")
        for market_row in sig.get("markets", []):
            if market_row.get("classification") in {"degrading", "weakening"} or market_row.get("risk_level") == "high":
                critical.append(f"{signal_type} / {market_row.get('market')}")
    critical_str = "\n".join(f"- {item}" for item in critical) if critical else "None"

    content = f"""**Signal Quality Audit: {final_report['date']}**

**Summary:**
- Total Types: {summary['total_signal_types']}
- Degrading Segments: {summary['degrading_segments_count']}
- High Risk Segments: {summary['high_risk_segments_count']}

**Critical Segments (High Risk/Degrading/Weakening):**
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

    if not db_url:
        logger.error("Missing DATABASE_URL")
        return

    # 2. Introspect
    inspector = SchemaInspector(db_url)
    schema_map = inspector.inspect()
    logger.info(f"Introspected schema: {schema_map}")
    
    # 3. Query
    builder = QueryBuilder(schema_map)
    queries = builder.build_queries()
    if not queries:
        logger.error("No queries generated. Check schema mapping.")
        return
        
    raw_results = execute_queries(db_url, queries)
    logger.info(f"Query results: {raw_results}")
    
    # 4. Deterministic Processing
    processor = MetricsProcessor(raw_results)
    audit_results = processor.process()
    
    # 5. LLM Interpretation
    audit_results["executive_interpretation"] = ""
    audit_results["optimization_suggestions"] = []
    if api_key:
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
        with open(prompt_path, "r") as f:
            prompt_tmpl = f.read()
        
        client = OpenAI(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt_tmpl.format(data=json.dumps(audit_results, default=str))},
                    {"role": "user", "content": "Provide commentary only. Do not change or recompute any metric."}
                ],
                response_format={"type": "json_object"}
            )
            llm_output = json.loads(response.choices[0].message.content)
            audit_results["executive_interpretation"] = str(
                llm_output.get("executive_interpretation", "")
            )
            suggestions = llm_output.get("optimization_suggestions", [])
            if isinstance(suggestions, list):
                audit_results["optimization_suggestions"] = [str(item) for item in suggestions][:3]
        except Exception as e:
            logger.error(f"LLM Interpretation failed: {e}")
    else:
        logger.warning("OPENAI_API_KEY missing: skipping interpretation step")

    # 6. Save Output
    audit_results["date"] = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    
    filename = f"quality_report_v2_{audit_results['date']}.json"
    file_path = os.path.join(out_dir, filename)
    with open(file_path, "w") as f:
        json.dump(audit_results, f, indent=2)
    
    logger.info(f"Audit saved to {file_path}")

    # 7. Terminal summary
    summary = audit_results["summary"]
    print(f"total signal types: {summary['total_signal_types']}")
    print(f"degrading segments count: {summary['degrading_segments_count']}")
    print(f"high risk segments count: {summary['high_risk_segments_count']}")
    print("top 3 worst drifts:")
    top_3 = summary.get("top_3_worst_drifts", [])
    if not top_3:
        print("- none")
    else:
        for row in top_3:
            print(
                f"- {row['signal_type']} / {row['market']}: "
                f"drift={row['drift']:.6f}, sample_7d={row['sample_7d']}"
            )

    # 8. Discord
    post_to_discord(discord_webhook, audit_results)

if __name__ == "__main__":
    main()
