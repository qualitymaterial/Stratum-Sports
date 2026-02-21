"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { getMe } from "@/lib/api";
import { User } from "@/lib/types";

const TOKEN_KEY = "stratum_token";
const USER_KEY = "stratum_user";
const isBrowser = () => typeof window !== "undefined";

export function setSession(token: string, user: User) {
  if (!isBrowser()) {
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  if (!isBrowser()) {
    return;
  }
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken(): string {
  if (!isBrowser()) {
    return "";
  }
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getStoredUser(): User | null {
  if (!isBrowser()) {
    return null;
  }
  const value = localStorage.getItem(USER_KEY);
  if (!value) {
    return null;
  }
  try {
    return JSON.parse(value) as User;
  } catch {
    return null;
  }
}

export function useCurrentUser(redirectToLogin = true) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<User | null>(getStoredUser());
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      setUser(null);
      if (redirectToLogin) {
        router.replace("/login");
      }
      return;
    }

    setLoading(true);
    try {
      const current = await getMe(token);
      localStorage.setItem(USER_KEY, JSON.stringify(current));
      setUser(current);
      setError(null);
    } catch (err) {
      clearSession();
      setUser(null);
      setError(err instanceof Error ? err.message : "Authentication failed");
      if (redirectToLogin) {
        router.replace("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [redirectToLogin, router]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  return useMemo(
    () => ({ user, loading, error, refreshUser, token: getToken() }),
    [user, loading, error, refreshUser],
  );
}
