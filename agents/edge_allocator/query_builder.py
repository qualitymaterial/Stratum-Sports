class QueryBuilder:
    """Builds read-only SQL queries for segmented CLV performance."""

    @staticmethod
    def build_segment_metrics_query() -> str:
        # Uses clv_records as the performance source and joins signals for metadata fallback.
        return """
            SELECT
                COALESCE(NULLIF(c.signal_type, ''), NULLIF(s.signal_type, ''), 'UNKNOWN') AS signal_type,
                COALESCE(NULLIF(c.market, ''), NULLIF(s.market, ''), 'UNKNOWN') AS market,
                COUNT(*)::int AS sample_30d,
                COUNT(*) FILTER (
                    WHERE c.computed_at >= NOW() - INTERVAL '7 days'
                )::int AS sample_7d,
                (
                    SUM(
                        CASE
                            WHEN COALESCE(c.clv_line, c.clv_prob) > 0 THEN 1
                            ELSE 0
                        END
                    )::float
                    / NULLIF(COUNT(*), 0)
                ) AS pos_rate_30d,
                (
                    SUM(
                        CASE
                            WHEN c.computed_at >= NOW() - INTERVAL '7 days'
                                 AND COALESCE(c.clv_line, c.clv_prob) > 0 THEN 1
                            ELSE 0
                        END
                    )::float
                    / NULLIF(
                        COUNT(*) FILTER (
                            WHERE c.computed_at >= NOW() - INTERVAL '7 days'
                        ),
                        0
                    )
                ) AS pos_rate_7d,
                AVG(COALESCE(c.clv_line, c.clv_prob)) AS avg_clv_30d,
                AVG(COALESCE(c.clv_line, c.clv_prob)) FILTER (
                    WHERE c.computed_at >= NOW() - INTERVAL '7 days'
                ) AS avg_clv_7d
            FROM clv_records c
            LEFT JOIN signals s
                ON s.id = c.signal_id
            WHERE c.computed_at >= NOW() - INTERVAL '30 days'
              AND COALESCE(c.clv_line, c.clv_prob) IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 2
        """
