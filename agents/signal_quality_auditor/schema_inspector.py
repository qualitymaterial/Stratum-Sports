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
            "clv": {
                "table": None,
                "timestamp_col": None,
                "type_col": None,
                "market_col": None,
                "line_col": None,
                "prob_col": None,
            },
            "signals": {"table": None, "timestamp_col": None, "type_col": None},
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
                    schema_map["clv"]["timestamp_col"] = (
                        "computed_at"
                        if "computed_at" in cols
                        else next((c for c in cols if "computed" in c or "time" in c or c.endswith("_at")), None)
                    )
                    schema_map["clv"]["type_col"] = (
                        "signal_type" if "signal_type" in cols else next((c for c in cols if "type" in c), None)
                    )
                    schema_map["clv"]["market_col"] = (
                        "market" if "market" in cols else next((c for c in cols if "market" in c), None)
                    )
                    schema_map["clv"]["line_col"] = "clv_line" if "clv_line" in cols else None
                    schema_map["clv"]["prob_col"] = "clv_prob" if "clv_prob" in cols else None

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
