import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getAccessToken, setAccessToken } from "@/lib/api";

interface AuthState {
  accessToken: string | null;
  user: { id: string; email: string; username: string; role: string } | null;
  setTokens: (access: string) => void;
  setUser: (user: AuthState["user"]) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

/** Bearer token for API calls (sessionStorage is source of truth after refresh). */
export function useApiToken(): string | null {
  const accessToken = useAuthStore((s) => s.accessToken);
  return getAccessToken() || accessToken;
}

/** @deprecated Prefer useApiToken() — reads sessionStorage + Zustand. */
export const useAccessToken = useApiToken;

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      setTokens: (access) => {
        setAccessToken(access);
        set({ accessToken: access });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        setAccessToken(null);
        set({ accessToken: null, user: null });
      },
      isAuthenticated: () => !!get().accessToken || !!getAccessToken(),
    }),
    {
      name: "streamshield-auth",
      partialize: (state) => ({ user: state.user }),
      onRehydrateStorage: () => (state) => {
        if (!state?.user) return;
        const stored = getAccessToken();
        if (stored) state?.setTokens(stored);
      },
    },
  ),
);
