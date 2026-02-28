FROM python:3.12-slim

WORKDIR /app

# Copy package files
COPY pyproject.toml .
COPY stratum_mcp/ ./stratum_mcp/

# Install the package
RUN pip install --no-cache-dir -e .

EXPOSE 8001

# Server reads STRATUM_API_KEY, STRATUM_API_BASE_URL, MCP_HOST, MCP_PORT from env
CMD ["stratum-mcp"]
