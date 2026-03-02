import logging

logger = logging.getLogger(__name__)

class QueryBuilder:
    def __init__(self, schema_map):
        self.schema_map = schema_map

    def build_queries(self):
        queries = {}
        
        # 1. CLV Stat Queries (7d vs 30d)
        clv = self.schema_map.get("clv")
        if clv and clv["table"] and clv["timestamp_col"] and clv["value_col"]:
            queries["clv_stats"] = f"""
                SELECT 
                    '7d' as period,
                    COUNT(*) as total_count,
                    AVG({clv["value_col"]}) as avg_value
                FROM {clv["table"]}
                WHERE {clv["timestamp_col"]} >= NOW() - INTERVAL '7 days'
                UNION ALL
                SELECT 
                    '30d' as period,
                    COUNT(*) as total_count,
                    AVG({clv["value_col"]}) as avg_value
                FROM {clv["table"]}
                WHERE {clv["timestamp_col"]} >= NOW() - INTERVAL '30 days'
            """

        # 2. 24h Signal Volume
        signals = self.schema_map.get("signals")
        if signals and signals["table"] and signals["timestamp_col"] and signals["type_col"]:
            queries["signal_volume"] = f"""
                SELECT 
                    {signals["type_col"]} as type,
                    COUNT(*) as count
                FROM {signals["table"]}
                WHERE {signals["timestamp_col"]} >= NOW() - INTERVAL '24 hours'
                GROUP BY {signals["type_col"]}
                ORDER BY count DESC
            """

        # 3. 24h Error Counts
        errors = self.schema_map.get("errors")
        if errors and errors["table"] and errors["timestamp_col"] and errors["message_col"]:
            queries["error_report"] = f"""
                SELECT 
                    {errors["message_col"]} as msg,
                    COUNT(*) as count
                FROM {errors["table"]}
                WHERE {errors["timestamp_col"]} >= NOW() - INTERVAL '24 hours'
                GROUP BY 1
                ORDER BY count DESC
                LIMIT 10
            """
        
        return queries
