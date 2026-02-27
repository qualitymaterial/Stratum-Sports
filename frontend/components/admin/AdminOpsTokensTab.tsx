"use client";

export function AdminOpsTokensTab() {
  return (
    <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
      <p className="text-xs uppercase tracking-wider text-textMute">Ops Service Tokens</p>
      <p className="mt-3 text-sm text-textMute">
        Ops service token management UI coming soon. Use the API endpoints directly for now:
      </p>
      <ul className="mt-2 space-y-1 text-sm text-textMute">
        <li>
          <code className="text-xs text-accent">GET /api/v1/admin/ops-tokens</code> — list tokens
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens</code> — issue token
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens/:id/revoke</code> — revoke
        </li>
        <li>
          <code className="text-xs text-accent">POST /api/v1/admin/ops-tokens/:id/rotate</code> — rotate
        </li>
      </ul>
    </div>
  );
}
