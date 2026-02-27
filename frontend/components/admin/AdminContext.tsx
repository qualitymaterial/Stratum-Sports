"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import {
  getAdminUsers,
  getAdminUserBilling,
  getAdminUserApiPartnerKeys,
  getAdminUserApiPartnerEntitlement,
} from "@/lib/api";
import {
  AdminApiPartnerEntitlement,
  AdminApiPartnerKeyList,
  AdminBillingOverview,
  AdminUserSearchItem,
  User,
} from "@/lib/types";

type AdminContextValue = {
  token: string;
  user: User;

  userSearchQuery: string;
  setUserSearchQuery: (q: string) => void;
  userSearchResults: AdminUserSearchItem[];
  userSearchLoading: boolean;
  userSearchError: string | null;

  mutationUserId: string;
  setMutationUserId: (id: string) => void;
  mutationReason: string;
  setMutationReason: (r: string) => void;
  mutationStepUpPassword: string;
  setMutationStepUpPassword: (p: string) => void;
  mutationConfirmPhrase: string;
  setMutationConfirmPhrase: (p: string) => void;
  mutationMfaCode: string;
  setMutationMfaCode: (c: string) => void;
  mutationLoading: boolean;
  mutationResult: string | null;
  mutationError: string | null;

  canProceedMutation: () => boolean;
  executeMutation: (fn: () => Promise<string>) => Promise<void>;

  billingSummary: AdminBillingOverview | null;
  billingLoading: boolean;
  billingError: string | null;
  refreshBilling: () => void;

  partnerKeysSummary: AdminApiPartnerKeyList | null;
  partnerKeysLoading: boolean;
  partnerKeysError: string | null;
  refreshPartnerKeys: () => void;

  partnerEntitlement: AdminApiPartnerEntitlement | null;
  setPartnerEntitlement: (e: AdminApiPartnerEntitlement | null) => void;
  partnerEntitlementLoading: boolean;
  partnerEntitlementError: string | null;
  refreshPartnerEntitlement: () => void;

  onSelectUser: (userId: string) => void;
  latestIssuedApiKey: string | null;
  setLatestIssuedApiKey: (k: string | null) => void;

  selectedUserDefaults: {
    tier: "free" | "pro";
    role: string;
    active: "active" | "inactive";
  } | null;
};

const Ctx = createContext<AdminContextValue | null>(null);

export function useAdminContext(): AdminContextValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useAdminContext must be inside AdminContextProvider");
  return value;
}

export function AdminContextProvider({
  token,
  user,
  children,
}: {
  token: string;
  user: User;
  children: React.ReactNode;
}) {
  const [userSearchQuery, setUserSearchQuery] = useState("");
  const [userSearchResults, setUserSearchResults] = useState<AdminUserSearchItem[]>([]);
  const [userSearchLoading, setUserSearchLoading] = useState(false);
  const [userSearchError, setUserSearchError] = useState<string | null>(null);

  const [mutationUserId, setMutationUserId] = useState("");
  const [mutationReason, setMutationReason] = useState("");
  const [mutationStepUpPassword, setMutationStepUpPassword] = useState("");
  const [mutationConfirmPhrase, setMutationConfirmPhrase] = useState("");
  const [mutationMfaCode, setMutationMfaCode] = useState("");
  const [mutationLoading, setMutationLoading] = useState(false);
  const [mutationResult, setMutationResult] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  const [billingSummary, setBillingSummary] = useState<AdminBillingOverview | null>(null);
  const [billingLoading, setBillingLoading] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);

  const [partnerKeysSummary, setPartnerKeysSummary] = useState<AdminApiPartnerKeyList | null>(null);
  const [partnerKeysLoading, setPartnerKeysLoading] = useState(false);
  const [partnerKeysError, setPartnerKeysError] = useState<string | null>(null);

  const [partnerEntitlement, setPartnerEntitlement] = useState<AdminApiPartnerEntitlement | null>(null);
  const [partnerEntitlementLoading, setPartnerEntitlementLoading] = useState(false);
  const [partnerEntitlementError, setPartnerEntitlementError] = useState<string | null>(null);

  const [latestIssuedApiKey, setLatestIssuedApiKey] = useState<string | null>(null);
  const [selectedUserDefaults, setSelectedUserDefaults] = useState<AdminContextValue["selectedUserDefaults"]>(null);

  const loadBilling = useCallback(
    async (userId: string) => {
      if (!token || !userId.trim()) {
        setBillingSummary(null);
        setBillingError(null);
        return;
      }
      setBillingLoading(true);
      setBillingError(null);
      try {
        setBillingSummary(await getAdminUserBilling(token, userId.trim()));
      } catch (err) {
        setBillingSummary(null);
        setBillingError(err instanceof Error ? err.message : "Failed to load billing state");
      } finally {
        setBillingLoading(false);
      }
    },
    [token],
  );

  const loadPartnerKeys = useCallback(
    async (userId: string) => {
      if (!token || !userId.trim()) {
        setPartnerKeysSummary(null);
        setPartnerKeysError(null);
        return;
      }
      setPartnerKeysLoading(true);
      setPartnerKeysError(null);
      try {
        setPartnerKeysSummary(await getAdminUserApiPartnerKeys(token, userId.trim()));
      } catch (err) {
        setPartnerKeysSummary(null);
        setPartnerKeysError(err instanceof Error ? err.message : "Failed to load API partner keys");
      } finally {
        setPartnerKeysLoading(false);
      }
    },
    [token],
  );

  const loadPartnerEntitlement = useCallback(
    async (userId: string) => {
      if (!token || !userId.trim()) {
        setPartnerEntitlement(null);
        setPartnerEntitlementError(null);
        return;
      }
      setPartnerEntitlementLoading(true);
      setPartnerEntitlementError(null);
      try {
        const payload = await getAdminUserApiPartnerEntitlement(token, userId.trim());
        setPartnerEntitlement(payload);
      } catch (err) {
        setPartnerEntitlement(null);
        setPartnerEntitlementError(err instanceof Error ? err.message : "Failed to load partner entitlement");
      } finally {
        setPartnerEntitlementLoading(false);
      }
    },
    [token],
  );

  const onSelectUser = useCallback(
    (nextUserId: string) => {
      setMutationUserId(nextUserId);
      setMutationError(null);
      setLatestIssuedApiKey(null);
      if (nextUserId) {
        void loadBilling(nextUserId);
        void loadPartnerKeys(nextUserId);
        void loadPartnerEntitlement(nextUserId);
        const selected = userSearchResults.find((item) => item.id === nextUserId);
        if (selected) {
          setUserSearchQuery(selected.email);
          setSelectedUserDefaults({
            tier: selected.tier === "pro" ? "pro" : "free",
            role: selected.admin_role ?? (selected.is_admin ? "super_admin" : "none"),
            active: selected.is_active ? "active" : "inactive",
          });
        }
      } else {
        setBillingSummary(null);
        setBillingError(null);
        setPartnerKeysSummary(null);
        setPartnerKeysError(null);
        setPartnerEntitlement(null);
        setPartnerEntitlementError(null);
        setSelectedUserDefaults(null);
      }
    },
    [loadBilling, loadPartnerKeys, loadPartnerEntitlement, userSearchResults],
  );

  const canProceedMutation = useCallback((): boolean => {
    if (!token || !mutationUserId.trim()) {
      setMutationError("User ID is required.");
      return false;
    }
    if (mutationReason.trim().length < 8) {
      setMutationError("Reason must be at least 8 characters.");
      return false;
    }
    if (mutationStepUpPassword.trim().length < 8) {
      setMutationError("Step-up password is required.");
      return false;
    }
    if (mutationConfirmPhrase.trim().toUpperCase() !== "CONFIRM") {
      setMutationError("Type CONFIRM to proceed.");
      return false;
    }
    if (user.mfa_enabled && mutationMfaCode.trim().length < 6) {
      setMutationError("MFA code is required (6 digits).");
      return false;
    }
    return true;
  }, [token, mutationUserId, mutationReason, mutationStepUpPassword, mutationConfirmPhrase, user.mfa_enabled, mutationMfaCode]);

  const executeMutation = useCallback(
    async (fn: () => Promise<string>) => {
      if (!canProceedMutation()) return;
      setMutationLoading(true);
      setMutationError(null);
      setMutationResult(null);
      try {
        const message = await fn();
        setMutationResult(message);
        setMutationStepUpPassword("");
        setMutationConfirmPhrase("");
        setMutationMfaCode("");
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : "Operation failed");
      } finally {
        setMutationLoading(false);
      }
    },
    [canProceedMutation],
  );

  // Debounced user search
  useEffect(() => {
    if (!token || !user?.is_admin) return;
    const query = userSearchQuery.trim();
    if (query.length < 2) {
      setUserSearchResults([]);
      setUserSearchError(null);
      setUserSearchLoading(false);
      return;
    }

    let canceled = false;
    const timer = window.setTimeout(async () => {
      setUserSearchLoading(true);
      setUserSearchError(null);
      try {
        const payload = await getAdminUsers(token, { q: query, limit: 12 });
        if (!canceled) setUserSearchResults(payload.items);
      } catch (err) {
        if (!canceled) {
          setUserSearchResults([]);
          setUserSearchError(err instanceof Error ? err.message : "User search failed");
        }
      } finally {
        if (!canceled) setUserSearchLoading(false);
      }
    }, 250);

    return () => {
      canceled = true;
      window.clearTimeout(timer);
    };
  }, [token, user?.is_admin, userSearchQuery]);

  const refreshBilling = useCallback(() => {
    if (mutationUserId.trim()) void loadBilling(mutationUserId.trim());
  }, [mutationUserId, loadBilling]);

  const refreshPartnerKeys = useCallback(() => {
    if (mutationUserId.trim()) void loadPartnerKeys(mutationUserId.trim());
  }, [mutationUserId, loadPartnerKeys]);

  const refreshPartnerEntitlement = useCallback(() => {
    if (mutationUserId.trim()) void loadPartnerEntitlement(mutationUserId.trim());
  }, [mutationUserId, loadPartnerEntitlement]);

  return (
    <Ctx.Provider
      value={{
        token,
        user,
        userSearchQuery,
        setUserSearchQuery,
        userSearchResults,
        userSearchLoading,
        userSearchError,
        mutationUserId,
        setMutationUserId,
        mutationReason,
        setMutationReason,
        mutationStepUpPassword,
        setMutationStepUpPassword,
        mutationConfirmPhrase,
        setMutationConfirmPhrase,
        mutationMfaCode,
        setMutationMfaCode,
        mutationLoading,
        mutationResult,
        mutationError,
        canProceedMutation,
        executeMutation,
        billingSummary,
        billingLoading,
        billingError,
        refreshBilling,
        partnerKeysSummary,
        partnerKeysLoading,
        partnerKeysError,
        refreshPartnerKeys,
        partnerEntitlement,
        setPartnerEntitlement,
        partnerEntitlementLoading,
        partnerEntitlementError,
        refreshPartnerEntitlement,
        onSelectUser,
        latestIssuedApiKey,
        setLatestIssuedApiKey,
        selectedUserDefaults,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
