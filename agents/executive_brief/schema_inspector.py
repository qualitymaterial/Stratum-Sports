import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SchemaInspector:
    def __init__(self, db_url):
        self.db_url = db_url

    def inspect(self):
        """
        Introspects the schema to find tables and columns for:
        - clv (clv_records)
        - signals (signals)
        - logs/errors (logs, error_logs, etc)
        """
        schema_map = {
            "clv": {"table": None, "timestamp_col": None, "value_col": None},
            "signals": {"table": None, "timestamp_col": None, "type_col": None},
            "errors": {"table": None, "timestamp_col": None, "message_col": None}
        }

        try:
            conn = psycopg2.connect(self.db_url)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. List all tables
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = [r['table_name'] for r in cur.fetchall()]
                logger.info(f"Found tables: {tables}")

                # 2. Match CLV table
                clv_table = next((t for t in tables if 'clv' in t), None)
                if clv_table:
                    schema_map["clv"]["table"] = clv_table
                    cols = self._get_columns(cur, clv_table)
                    schema_map["clv"]["timestamp_col"] = next((c for c in cols if 'time' in c or 'at' in c), None)
                    schema_map["clv"]["value_col"] = next((c for c in cols if 'prob' in c or 'line' in c), None)

                # 3. Match Signals table
                signal_table = next((t for t in tables if 'signal' in t), None)
                if signal_table:
                    schema_map["signals"]["table"] = signal_table
                    cols = self._get_columns(cur, signal_table)
                    schema_map["signals"]["timestamp_col"] = next((c for c in cols if 'created' in c or 'time' in c or 'at' in c), None)
                    schema_map["signals"]["type_col"] = next((c for c in cols if 'type' in c), None)

                # 4. Match Error/Log table
                error_table = next((t for t in tables if any(kw in t for kw in ['error', 'audit', 'log'])), None)
                if error_table:
                    schema_map["errors"]["table"] = error_table
                    cols = self._get_columns(cur, error_table)
                    schema_map["errors"]["timestamp_col"] = next((c for c in cols if 'time' in c or 'at' in c), None)
                    schema_map["errors"]["message_col"] = next((c for c in cols if 'msg' in c or 'desc' in c or 'detail' in c or 'type' in c), None)

            conn.close()
        except Exception as e:
            logger.error(f"Schema introspection failed: {e}")
            # We return partial map if possible
        
        return schema_map

    def _get_columns(self, cur, table_name):
        cur.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
        """)
        return [r['column_name'] for r in cur.fetchall()]

if __name__ == "__main__":
    import sys
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        sys.exit(1)
    inspector = SchemaInspector(db_url)
    print(inspector.inspect())
