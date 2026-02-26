# Scripts

## Trace Signal Feed

Use this helper to discover the current signal feed path (routes -> handlers -> service/query calls) and Discord dispatch locations:

```bash
python scripts/trace_signal_feed.py
```

The output is ranked and copy-pastable, for example:

```txt
ROUTE: /api/v1/intel/opportunities -> backend/app/api/routes/intel.py::get_opportunities() -> app.services.performance_intel::get_best_opportunities() [query:select,where,order_by,execute]
```
