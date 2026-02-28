import { User } from "@/lib/types";

export function hasProAccess(user: Pick<User, "tier" | "is_admin"> | null | undefined): boolean {
  if (!user) {
    return false;
  }
  return user.tier === "pro" || user.is_admin;
}

export function hasPartnerAccess(user: Pick<User, "has_partner_access" | "is_admin"> | null | undefined): boolean {
  if (!user) {
    return false;
  }
  return user.has_partner_access || user.is_admin;
}
