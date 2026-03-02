# Daily Executive Brief Agent

An automated intelligence agent that introspects the Stratum Sports production database and generates a structured executive brief using OpenAI gpt-4o.

## Features
- **Schema Aware**: Automatically detects `clv_records`, `signals`, and log tables.
- **Dynamic Queries**: Builds safe, read-only SELECT queries based on detected columns.
- **AI-Powered**: Uses OpenAI's Responses API to generate a structured JSON brief.
- **Dual Output**: Saves JSON locally and optionally posts a summary to Discord.
- **Production Safe**: 
    - Read-only database access.
    - Isolated directory and dependencies.
    - Zero modification to application logic.

## Safety First: Read-Only Database User
Before running, create a read-only user in your production Postgres:

```sql
-- Create read-only user
CREATE USER stratum_agent_ro WITH PASSWORD 'your_secure_password';

-- Grant access to public schema
GRANT USAGE ON SCHEMA public TO stratum_agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO stratum_agent_ro;

-- Ensure future tables are also read-only
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO stratum_agent_ro;
```

## Setup & Local Run

1. **Create Virtual Environment**:
   ```bash
   cd agents/executive_brief
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in:
   - `DATABASE_URL` (Use the read-only user created above!)
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL` (default: gpt-4o)
   - `DISCORD_WEBHOOK_URL` (Optional)

3. **Run Locally**:
   ```bash
   python main.py
   ```

Check the `out/` directory for the generated JSON report.

## Automation (Cron)
To run this daily at 8:00 AM, add a cron job (`crontab -e`):

```cron
0 8 * * * cd /path/to/stratum-sports/agents/executive_brief && ./venv/bin/python main.py >> agent.log 2>&1
```

## Directory Structure
- `main.py`: Orchestrator (entry point).
- `schema_inspector.py`: Database introspection logic.
- `query_builder.py`: Dynamic SQL generation.
- `prompt.txt`: System prompt and JSON schema definition.
- `out/`: Storage for generated reports.
