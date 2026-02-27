"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useMemo } from "react";

import { LoadingState } from "@/components/LoadingState";
import { hasAdminPermission } from "@/lib/adminPermissions";
import { useCurrentUser } from "@/lib/auth";

import { ADMIN_TABS, AdminTabKey, DEFAULT_TAB } from "@/components/admin/adminTabs";
import { AdminTabBar } from "@/components/admin/AdminTabBar";
import { AdminContextProvider } from "@/components/admin/AdminContext";
import { AdminOverviewTab } from "@/components/admin/AdminOverviewTab";
import { AdminUsersTab } from "@/components/admin/AdminUsersTab";
import { AdminBillingTab } from "@/components/admin/AdminBillingTab";
import { AdminApiPartnersTab } from "@/components/admin/AdminApiPartnersTab";
import { AdminOperationsTab } from "@/components/admin/AdminOperationsTab";
import { AdminAuditTab } from "@/components/admin/AdminAuditTab";
import { AdminSecurityTab } from "@/components/admin/AdminSecurityTab";

export default function AdminPage() {
  const { user, loading, token } = useCurrentUser(true);
  const searchParams = useSearchParams();
  const router = useRouter();

  const visibleTabs = useMemo(() => {
    if (!user?.is_admin) return [];
    return ADMIN_TABS.filter((tab) =>
      tab.requiredPermissions.some((perm) => hasAdminPermission(user, perm)),
    );
  }, [user]);

  const rawTab = searchParams.get("tab") as AdminTabKey | null;
  const activeTab =
    rawTab && visibleTabs.some((t) => t.key === rawTab)
      ? rawTab
      : visibleTabs[0]?.key ?? DEFAULT_TAB;

  const setActiveTab = (key: AdminTabKey) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", key);
    router.replace(`?${params.toString()}`);
  };

  if (loading || !user) {
    return <LoadingState label="Loading admin panel..." />;
  }

  if (!user.is_admin) {
    return (
      <section className="space-y-3">
        <h1 className="text-xl font-semibold">Admin</h1>
        <div className="rounded-xl border border-borderTone bg-panel p-5 text-sm text-textMute shadow-terminal">
          <p className="text-textMain">Admin access is required for this page.</p>
          <p className="mt-2">
            Go back to{" "}
            <Link href="/app/dashboard" className="text-accent hover:underline">
              Dashboard
            </Link>
            .
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Admin</h1>
        <p className="text-sm text-textMute">Current account role and operational access scope.</p>
      </header>

      <AdminTabBar tabs={visibleTabs} activeTab={activeTab} onTabChange={setActiveTab} />

      <AdminContextProvider token={token!} user={user}>
        {activeTab === "overview" && <AdminOverviewTab token={token!} user={user} />}
        {activeTab === "users" && <AdminUsersTab />}
        {activeTab === "billing" && <AdminBillingTab />}
        {activeTab === "api-partners" && <AdminApiPartnersTab />}
        {activeTab === "operations" && <AdminOperationsTab token={token!} user={user} />}
        {activeTab === "audit" && <AdminAuditTab token={token!} user={user} />}
        {activeTab === "security" && <AdminSecurityTab token={token!} />}
      </AdminContextProvider>
    </section>
  );
}
