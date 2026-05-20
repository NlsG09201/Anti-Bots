import { create } from "zustand";
import { persist } from "zustand/middleware";
import { bootstrapAuthSession, getAccessToken, setAccessToken } from "@/lib/api";

interface AuthState {
  accessToken: string | null;
  user: { id: string; email: string; username: string; role: string } | null;
  setTokens: (access: string) => void;
  setUser: (user: AuthState["user"]) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

/** Bearer token for API calls (Zustand + sessionStorage fallback). */
export function useApiToken(): string | null {
  const accessToken = useAuthStore((s) => s.accessToken);
  return accessToken || getAccessToken();
}

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
        void bootstrapAuthSession().then((token) => {
          if (token) state?.setTokens(token);
        });
      },
    },
  ),
);
