import logging

logger = logging.getLogger(__name__)

class QueryBuilder:
    def __init__(self, schema_map):
        self.schema_map = schema_map

    def build_queries(self):
        queries = {}
        
        clv = self.schema_map.get("clv")
        if clv and clv["table"] and clv["timestamp_col"] and clv["value_col"] and clv["type_col"]:
            # Query and group by signal_type
            # 30d
            queries["clv_30d"] = f"""
                SELECT 
                    {clv["type_col"]} as signal_type,
                    COUNT(*) as total_samples,
                    AVG({clv["value_col"]}) as avg_clv,
                    SUM(CASE WHEN {clv["value_col"]} > 0 THEN 1 ELSE 0 END)::float / COUNT(*) as pos_rate
                FROM {clv["table"]}
                WHERE {clv["timestamp_col"]} >= NOW() - INTERVAL '30 days'
                GROUP BY 1
            """
            # 7d
            queries["clv_7d"] = f"""
                SELECT 
                    {clv["type_col"]} as signal_type,
                    COUNT(*) as total_samples,
                    AVG({clv["value_col"]}) as avg_clv,
                    SUM(CASE WHEN {clv["value_col"]} > 0 THEN 1 ELSE 0 END)::float / COUNT(*) as pos_rate
                FROM {clv["table"]}
                WHERE {clv["timestamp_col"]} >= NOW() - INTERVAL '7 days'
                GROUP BY 1
            """
        
        return queries
