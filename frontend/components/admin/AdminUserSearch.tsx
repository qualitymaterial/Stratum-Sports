"use client";

import { useAdminContext } from "./AdminContext";

export function AdminUserSearch() {
  const ctx = useAdminContext();

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <label className="text-xs text-textMute">
        Find User (Email or UUID)
        <input
          value={ctx.userSearchQuery}
          onChange={(e) => ctx.setUserSearchQuery(e.target.value)}
          placeholder="search@example.com or uuid"
          className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
        />
        <p className="mt-1 text-[11px] text-textMute">
          {ctx.userSearchLoading
            ? "Searching..."
            : ctx.userSearchQuery.trim().length < 2
              ? "Enter at least 2 characters."
              : `${ctx.userSearchResults.length} match(es)`}
        </p>
        {ctx.userSearchError && <p className="mt-1 text-[11px] text-negative">{ctx.userSearchError}</p>}
      </label>
      <label className="text-xs text-textMute">
        Search Results
        <select
          value={ctx.mutationUserId}
          onChange={(e) => ctx.onSelectUser(e.target.value)}
          className="mt-1 w-full rounded border border-borderTone bg-panelSoft px-2 py-1 text-sm text-textMain"
        >
          <option value="">Select user</option>
          {ctx.userSearchResults.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.email} • tier:{candidate.tier} • role:
              {candidate.admin_role ?? (candidate.is_admin ? "super_admin" : "none")} • status:
              {candidate.is_active ? "active" : "inactive"}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
