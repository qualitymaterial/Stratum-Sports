import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

class SchemaInspector:
    def __init__(self, db_url):
        self.db_url = db_url

    def inspect(self):
        """
        Introspects the schema to find tables and columns for:
        - clv (clv_records)
        - signals (signals)
        """
        schema_map = {
            "clv": {"table": None, "timestamp_col": None, "value_col": None, "type_col": None},
            "signals": {"table": None, "timestamp_col": None, "type_col": None}
        }

        # Psycopg2 prefers postgres:// and doesn't support +driver prefixes
        conn_str = self.db_url
        if "://" in conn_str:
            prefix, rest = conn_str.split("://", 1)
            if "postgres" in prefix:
                conn_str = "postgres://" + rest

        try:
            conn = psycopg2.connect(conn_str)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. List all tables
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                tables = [r['table_name'] for r in cur.fetchall()]
                logger.info(f"Found tables: {tables}")

                # 2. Match CLV table (clv_records)
                clv_table = next((t for t in tables if 'clv' in t), None)
                if clv_table:
                    schema_map["clv"]["table"] = clv_table
                    cols = self._get_columns(cur, clv_table)
                    schema_map["clv"]["timestamp_col"] = next((c for c in cols if 'computed' in c or 'time' in c or 'at' in c), None)
                    schema_map["clv"]["value_col"] = next((c for c in cols if 'clv_line' in c or 'avg_clv' in c or 'prob' in c or 'line' in c), None)
                    schema_map["clv"]["type_col"] = next((c for c in cols if 'signal_type' in c or 'type' in c), None)

                # 3. Match Signals table
                signal_table = next((t for t in tables if 'signal' in t and t != clv_table), None)
                if signal_table:
                    schema_map["signals"]["table"] = signal_table
                    cols = self._get_columns(cur, signal_table)
                    schema_map["signals"]["timestamp_col"] = next((c for c in cols if 'created' in c or 'time' in c or 'at' in c), None)
                    schema_map["signals"]["type_col"] = next((c for c in cols if 'type' in c), None)

            conn.close()
        except Exception as e:
            logger.error(f"Schema introspection failed: {e}")
        
        return schema_map

    def _get_columns(self, cur, table_name):
        cur.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
        """)
        return [r['column_name'] for r in cur.fetchall()]
