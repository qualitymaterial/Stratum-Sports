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
        logger.error(f"Execution failed: {e}")
    return results

def post_to_discord(webhook_url, brief_data):
    if not webhook_url:
        return
    
    date = brief_data.get("date", "Unknown")
    summary = brief_data.get("one_sentence_summary", "No summary")
    actions = "\n".join([f"- {a}" for a in brief_data.get("top_actions", [])[:3]])
    
    content = f"**Daily Executive Brief: {date}**\n\n> {summary}\n\n**Top Actions:**\n{actions}"
    
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
    logger.info(f"Introspected schema: {schema_map}")

    # 3. Build & Run Queries
    builder = QueryBuilder(schema_map)
    queries = builder.build_queries()
    query_results = execute_queries(db_url, queries)
    
    # 4. Agent Call
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    with open(prompt_path, "r") as f:
        prompt_tmpl = f.read()
    
    payload = {
        "schema": schema_map,
        "metrics": query_results
    }
    
    client = OpenAI(api_key=api_key)
    
    logger.info("Calling OpenAI Responses API...")
    try:
        # Use modernization as requested (Responses API / ChatCompletion as backup if not available in SDK version)
        # Note: 'responses.create' is the requested syntax
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt_tmpl.format(
                    data=json.dumps(payload, default=str),
                    today_date=datetime.now().strftime('%Y-%m-%d')
                )},
                {"role": "user", "content": "Generate today's executive brief."}
            ],
            response_format={"type": "json_object"}
        )
        brief_text = response.choices[0].message.content
        brief_data = json.loads(brief_text)
    except Exception as e:
        logger.error(f"Agent generation failed: {e}")
        # Save raw if possible
        raw_path = f"agents/executive_brief/out/executive_brief_raw_{datetime.now().strftime('%Y-%m-%d')}.txt"
        with open(raw_path, "w") as f:
            f.write(str(payload))
        return

    # 5. Output
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    
    filename = f"executive_brief_{datetime.now().strftime('%Y-%m-%d')}.json"
    file_path = os.path.join(out_dir, filename)
    
    with open(file_path, "w") as f:
        json.dump(brief_data, f, indent=2)
    
    logger.info(f"Brief saved to {file_path}")

    # 6. Discord
    post_to_discord(discord_webhook, brief_data)

if __name__ == "__main__":
    main()
