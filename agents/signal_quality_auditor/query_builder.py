import logging

logger = logging.getLogger(__name__)

class QueryBuilder:
    def __init__(self, schema_map):
        self.schema_map = schema_map

    def build_queries(self):
        queries = {}
        
        clv = self.schema_map.get("clv")
        if not clv:
            return queries

        table = clv.get("table")
        ts_col = clv.get("timestamp_col")
        type_col = clv.get("type_col")
        market_col = clv.get("market_col")
        line_col = clv.get("line_col")
        prob_col = clv.get("prob_col")

        if not table or not ts_col or not type_col or not market_col:
            return queries

        value_expr = None
        value_filter = None
        if line_col and prob_col:
            value_expr = f"COALESCE({line_col}, {prob_col})"
            value_filter = f"({line_col} IS NOT NULL OR {prob_col} IS NOT NULL)"
        elif line_col:
            value_expr = line_col
            value_filter = f"{line_col} IS NOT NULL"
        elif prob_col:
            value_expr = prob_col
            value_filter = f"{prob_col} IS NOT NULL"

        if value_expr and value_filter:
            # 30d segmented by signal type + market
            queries["clv_30d"] = f"""
                SELECT 
                    {type_col} as signal_type,
                    {market_col} as market,
                    COUNT(*) as total_samples,
                    AVG({value_expr}) as avg_clv,
                    SUM(CASE WHEN {value_expr} > 0 THEN 1 ELSE 0 END)::float / COUNT(*) as pos_rate
                FROM {table}
                WHERE {ts_col} >= NOW() - INTERVAL '30 days'
                  AND {value_filter}
                GROUP BY 1, 2
            """

            # 7d segmented by signal type + market
            queries["clv_7d"] = f"""
                SELECT 
                    {type_col} as signal_type,
                    {market_col} as market,
                    COUNT(*) as total_samples,
                    AVG({value_expr}) as avg_clv,
                    SUM(CASE WHEN {value_expr} > 0 THEN 1 ELSE 0 END)::float / COUNT(*) as pos_rate
                FROM {table}
                WHERE {ts_col} >= NOW() - INTERVAL '7 days'
                  AND {value_filter}
                GROUP BY 1, 2
            """
        
        return queries
