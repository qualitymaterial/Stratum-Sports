import { createDocsMetadata } from "@/app/docs/docsConfig";
import DocsPage from "@/components/docs/DocsPage";
import DocsVerifiedNote from "@/components/docs/DocsVerifiedNote";

export const metadata = createDocsMetadata({
    title: "MCP Server",
    description: "Exposing Stratum Sports intelligence via Model Context Protocol (MCP).",
    path: "/docs/mcp-server",
});

export default function DocsMCPServerPage() {
    return (
        <DocsPage
            title="MCP Server"
            description="The Stratum MCP Server enables AI agents (like Claude Desktop and Cursor) to natively call Stratum intelligence tools."
        >
            <section className="space-y-3">
                <h2 className="text-xl font-semibold">Overview</h2>
                <p className="text-textMute">
                    The Stratum Sports MCP Server is an SSE-ready [Model Context Protocol](https://modelcontextprotocol.io/) server. It provides a bridge between AI agents and the Stratum Sports intelligence API, exposing 13 specialized tools for signal analysis, CLV tracking, and market consensus.
                </p>
                <div className="rounded border border-borderTone bg-panelSoft p-4 text-sm text-textMute">
                    <p className="font-semibold text-textMain">Pro Tier Required</p>
                    <p className="mt-1">
                        Access to the MCP server is gated to **Pro** and **Enterprise** accounts. The server performs an identity check on startup and rejects connections from lower tiers.
                    </p>
                </div>
            </section>

            <section className="space-y-3">
                <h2 className="text-xl font-semibold">Installation & Setup</h2>
                <p className="text-textMute">
                    The MCP server is distributed as a Python package in the repository root at <code className="rounded bg-bg px-1.5 py-0.5 text-accent">/mcp</code>.
                </p>
                <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
                    {`# 1. Install dependencies
cd mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure environment
copy .env.example .env
# Set STRATUM_API_KEY to your Pro-tier token

# 3. Launch the server
stratum-mcp`}
                </pre>
                <p className="text-textMute">
                    On successful startup, the server will log: <code className="rounded bg-bg px-1.5 py-0.5 text-accent">✅ Pro-tier verified. Starting Stratum MCP SSE server on 0.0.0.0:8001</code>.
                </p>
            </section>

            <section className="space-y-3">
                <h2 className="text-xl font-semibold">Claude Desktop Integration</h2>
                <p className="text-textMute">
                    To use Stratum intelligence inside Claude Desktop, add the following to your <code className="rounded bg-bg px-1.5 py-0.5 text-accent">claude_desktop_config.json</code>:
                </p>
                <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
                    {`{
  "mcpServers": {
    "stratum-sports": {
      "url": "http://localhost:8001/sse",
      "type": "sse"
    }
  }
}`}
                </pre>
                <p className="text-textMute">
                    Configuration file locations:
                    <ul className="mt-1 list-disc pl-5">
                        <li>macOS: <code className="text-accent underline">~/Library/Application Support/Claude/claude_desktop_config.json</code></li>
                        <li>Windows: <code className="text-accent underline">%APPDATA%\Claude\claude_desktop_config.json</code></li>
                    </ul>
                </p>
            </section>

            <section className="space-y-3">
                <h2 className="text-xl font-semibold">Available Tools</h2>
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-left text-sm text-textMute">
                        <thead>
                            <tr className="border-b border-borderTone text-textMain">
                                <th className="py-2 pr-4 font-semibold">Tool Name</th>
                                <th className="py-2 font-semibold">Capability</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-borderTone">
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">get_signal_quality</td>
                                <td className="py-2">Primary signal feed (STEAM, MOVE, KEY_CROSS, etc.)</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">get_clv_records</td>
                                <td className="py-2">Individual CLV records for entry vs. close line analysis</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">get_opportunities</td>
                                <td className="py-2">Best current plays ranked by edge and conviction</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">get_consensus</td>
                                <td className="py-2">Aggregated market consensus snapshot for active games</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">list_games</td>
                                <td className="py-2">Upcoming game schedule with event IDs and timings</td>
                            </tr>
                            <tr>
                                <td className="py-2 pr-4 font-mono text-accent">get_actionable_books</td>
                                <td className="py-2">Book recommendations optimized for the specific signal</td>
                            </tr>
                        </tbody>
                    </table>
                    <p className="mt-4 text-xs italic">Plus 7 additional utility and aggregation tools.</p>
                </div>
            </section>

            <section className="space-y-3">
                <h2 className="text-xl font-semibold">Deployment via Docker</h2>
                <p className="text-textMute">
                    For production or cloud deployment, use the bundled Dockerfile:
                </p>
                <pre className="overflow-x-auto rounded border border-borderTone bg-bg p-4 text-xs text-textMain">
                    {`docker build -t stratum-mcp ./mcp
docker run -d \\
  -e STRATUM_API_KEY=<token> \\
  -p 8001:8001 \\
  stratum-mcp`}
                </pre>
            </section>

            <DocsVerifiedNote />
        </DocsPage>
    );
}
