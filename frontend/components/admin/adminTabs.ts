import { AdminPermission } from "@/lib/adminPermissions";

export type AdminTabKey = "overview" | "users" | "billing" | "api-partners" | "operations" | "audit" | "security";

export type AdminTabConfig = {
  key: AdminTabKey;
  label: string;
  requiredPermissions: AdminPermission[];
};

export const ADMIN_TABS: AdminTabConfig[] = [
  {
    key: "overview",
    label: "Overview",
    requiredPermissions: ["admin_read"],
  },
  {
    key: "users",
    label: "Users",
    requiredPermissions: ["user_tier_write", "user_role_write", "user_status_write", "user_password_reset_write"],
  },
  {
    key: "billing",
    label: "Billing",
    requiredPermissions: ["billing_write"],
  },
  {
    key: "api-partners",
    label: "API Partners",
    requiredPermissions: ["partner_api_write"],
  },
  {
    key: "operations",
    label: "Operations",
    requiredPermissions: ["ops_token_write"],
  },
  {
    key: "audit",
    label: "Audit",
    requiredPermissions: ["admin_read"],
  },
  {
    key: "security",
    label: "Security",
    requiredPermissions: ["admin_read"],
  },
];

export const DEFAULT_TAB: AdminTabKey = "overview";
