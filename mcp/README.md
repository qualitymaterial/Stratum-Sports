# Stratum Sports MCP Server

An SSE-ready [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes the Stratum Sports intelligence API as AI-callable tools. Use it with **Claude Desktop**, **Cursor**, or any MCP-compatible agent.

> **Pro tier required.** The server refuses to start if your API key does not belong to a Pro or higher Stratum account.

---

## Quick Start (Local)

### 1. Install

```bash
cd mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set your Stratum API key:
#   STRATUM_API_KEY=your_token_here
#   STRATUM_API_BASE_URL=https://api.stratumsports.com
```

### 3. Run

```bash
stratum-mcp
```

Expected output if key is Pro+:
```
✅ Pro-tier verified. Starting Stratum MCP SSE server on 0.0.0.0:8001
```

If the key is free-tier:
```
🔒 Pro-tier gate failed: Stratum MCP requires a Pro+ subscription. Current tier: 'free'.
```

---

## Claude Desktop Integration

Add this to your Claude Desktop `claude_desktop_config.json` (or paste the bundled `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "stratum-sports": {
      "url": "http://localhost:8001/sse",
      "type": "sse"
    }
  }
}
```

On macOS, the config file is at:
`~/Library/Application Support/Claude/claude_desktop_config.json`

Restart Claude Desktop after editing. You should see **Stratum Sports** under MCP tools.

---

## Docker / Remote Deployment

Build and run as a container (exposes SSE on port 8001):

```bash
cd mcp
docker build -t stratum-mcp .
docker run -d \
  -e STRATUM_API_KEY=your_token_here \
  -e STRATUM_API_BASE_URL=https://api.stratumsports.com \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=8001 \
  -p 8001:8001 \
  --name stratum-mcp \
  stratum-mcp
```

For remote clients, point your MCP config at `http://YOUR_SERVER_IP:8001/sse`.

---

## Verification

```bash
# With the server running:
npx @modelcontextprotocol/inspector http://localhost:8001/sse
```

The inspector should list all 13 tools.

---

## Available Tools

| Tool | Description |
|---|---|
| `get_signal_quality` | Primary signal feed — STEAM, MOVE, KEY_CROSS, DISLOCATION, etc. |
| `get_signals_weekly_summary` | Rolled-up weekly signal quality metrics |
| `get_signal_lifecycle` | Signal timing distribution and CLV capture by time bucket |
| `get_clv_records` | Individual CLV records (entry vs. close line) |
| `get_clv_summary` | Aggregated CLV performance by signal type and market |
| `get_clv_recap` | Time-series CLV trends (daily or weekly grain) |
| `get_clv_scorecards` | Trust grades (A–F) per signal-type/market bucket |
| `get_opportunities` | Best current plays ranked by edge and conviction |
| `get_consensus` | Latest market consensus snapshot for a game |
| `list_games` | Upcoming games with event IDs, teams, tip-off times |
| `get_game_detail` | Full game detail — odds, signals, consensus |
| `list_watchlist` | Your bookmarked games |
| `get_actionable_books` | Recommended books for a specific signal |
| `get_actionable_books_batch` | Batch book recommendations for multiple signals |

---

## Pro-Tier Enforcement

The server calls `GET /api/v1/auth/me` on startup to verify the provided `STRATUM_API_KEY` belongs to a `pro` or `enterprise` account (or has `has_partner_access`). If the check fails:

- **On startup:** the process exits immediately with a clear error.
- **Per tool call:** a cached check (5-minute TTL) re-validates the key and returns a `PermissionError` if the tier has changed.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `STRATUM_API_KEY` | ✅ | — | Stratum bearer token (Pro+ required) |
| `STRATUM_API_BASE_URL` | ✅ | `https://api.stratumsports.com` | API base URL |
| `MCP_HOST` | | `0.0.0.0` | Host to bind the SSE server |
| `MCP_PORT` | | `8001` | Port for the SSE server |
