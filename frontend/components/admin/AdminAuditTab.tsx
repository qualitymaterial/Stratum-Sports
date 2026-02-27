"use client";

import { useEffect, useState } from "react";

import { getAdminAuditLogs } from "@/lib/api";
import { AdminAuditLogList, User } from "@/lib/types";

type Props = { token: string; user: User };

export function AdminAuditTab({ token, user }: Props) {
  const [auditLogs, setAuditLogs] = useState<AdminAuditLogList | null>(null);
  const [auditActionType, setAuditActionType] = useState("");
  const [auditTargetIdFilter, setAuditTargetIdFilter] = useState("");

  const loadAudit = async () => {
    if (!token || !user?.is_admin) return;
    const payload = await getAdminAuditLogs(token, {
      limit: 20,
      offset: 0,
      action_type: auditActionType || undefined,
      target_id: auditTargetIdFilter || undefined,
    });
    setAuditLogs(payload);
  };

  useEffect(() => {
    void loadAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.is_admin]);

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-textMute">Admin Audit Log</p>
            <p className="mt-1 text-xs text-textMute">
              Newest entries first. Use filters to narrow results.
            </p>
          </div>
          <button
            onClick={() => void loadAudit()}
            className="rounded border border-borderTone px-3 py-1.5 text-xs uppercase tracking-wider text-textMute transition hover:border-accent hover:text-accent"
          >
            Refresh Audit
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-xs text-textMute">
            Action Type Filter
            <input
              value={auditActionType}
              onChange={(e) => setAuditActionType(e.target.value)}
              placeholder="admin.user.role.update"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
          <label className="text-xs text-textMute">
            Target ID Filter
            <input
              value={auditTargetIdFilter}
              onChange={(e) => setAuditTargetIdFilter(e.target.value)}
              placeholder="target user uuid"
              className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
            />
          </label>
        </div>

        <div className="mt-4 overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-textMute">
                <th className="border-b border-borderTone py-2">Created</th>
                <th className="border-b border-borderTone py-2">Action</th>
                <th className="border-b border-borderTone py-2">Target</th>
                <th className="border-b border-borderTone py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {(auditLogs?.items ?? []).map((row) => (
                <tr key={row.id}>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.action_type}</div>
                    <div className="text-xs text-textMute">actor {row.actor_user_id}</div>
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.target_type}</div>
                    <div className="text-xs text-textMute">{row.target_id ?? "-"}</div>
                  </td>
                  <td className="border-b border-borderTone/50 py-2 text-textMain">
                    <div>{row.reason}</div>
                    {row.request_id && (
                      <div className="text-xs text-textMute">req {row.request_id}</div>
                    )}
                  </td>
                </tr>
              ))}
              {(auditLogs?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={4} className="py-3 text-xs text-textMute">
                    No audit events match current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-borderTone bg-panel p-5 shadow-terminal">
        <p className="text-xs uppercase tracking-wider text-textMute">Important Notes</p>
        <div className="mt-3 space-y-2 text-sm text-textMute">
          <p>Admin UI currently focuses on access control mutations and audit visibility.</p>
          <p>
            Role changes require super-admin permission; tier updates allow broader admin roles.
          </p>
          <p>
            Most operational actions (deploy, deep backfills, and ops break-glass flows) remain
            script-driven or protected internal endpoints.
          </p>
        </div>
      </div>
    </div>
  );
}
