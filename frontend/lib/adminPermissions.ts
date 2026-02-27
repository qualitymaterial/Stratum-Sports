import { AdminRole, User } from "@/lib/types";

export type AdminPermission =
  | "admin_read"
  | "user_tier_write"
  | "user_role_write"
  | "user_status_write"
  | "user_password_reset_write"
  | "billing_write"
  | "partner_api_write"
  | "ops_token_write";

const ROLE_PERMISSIONS: Record<AdminRole, AdminPermission[]> = {
  super_admin: [
    "admin_read",
    "user_tier_write",
    "user_role_write",
    "user_status_write",
    "user_password_reset_write",
    "billing_write",
    "partner_api_write",
    "ops_token_write",
  ],
  ops_admin: [
    "admin_read",
    "user_tier_write",
    "user_status_write",
    "user_password_reset_write",
    "ops_token_write",
  ],
  support_admin: [
    "admin_read",
    "user_tier_write",
    "user_status_write",
    "user_password_reset_write",
  ],
  billing_admin: [
    "admin_read",
    "billing_write",
    "partner_api_write",
  ],
};

export function effectiveAdminRole(user: Pick<User, "is_admin" | "admin_role">): AdminRole | null {
  if (user.admin_role) return user.admin_role;
  if (user.is_admin) return "super_admin";
  return null;
}

export function hasAdminPermission(
  user: Pick<User, "is_admin" | "admin_role">,
  permission: AdminPermission,
): boolean {
  const role = effectiveAdminRole(user);
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false;
}
