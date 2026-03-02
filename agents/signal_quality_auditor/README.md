# Signal Quality Auditor

A production-safe, read-only internal auditing agent that monitors historical Closing Line Value (CLV) performance across signal types.

## What this agent protects
This agent detects "alpha decay" in betting signals. By comparing 7-day performance against 30-day baselines, it identifies when specific signal classes (e.g., specific algorithms or source feeds) are starting to lose their edge or are being "solved" by the market.

## Why deterministic thresholds?
Statistical significance and trend detection are computed in Python to ensure accuracy and reproducibility. The LLM is used only for high-level interpretation and strategic suggestions, ensuring that all reported metrics are technically sound.

## Installation
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your DATABASE_URL and OPENAI_API_KEY
```

## How to run manually
```bash
python main.py
```

## How to schedule via cron
Add the following to your crontab (example for daily at 9:00 AM):
```bash
0 9 * * * cd /path/to/stratum-sports && python3 agents/signal_quality_auditor/main.py >> agents/signal_quality_auditor/audit.log 2>&1
```

## Integration with Executive Brief
The output of this agent (`out/quality_report_YYYY-MM-DD.json`) can be injected into the `Daily Executive Brief Agent` to provide a higher-level summary of signal health to leadership.
