import { create } from "zustand";
import { persist } from "zustand/middleware";
import { getAccessToken, refreshAccessToken, setAccessToken } from "@/lib/api";

interface AuthState {
  accessToken: string | null;
  user: { id: string; email: string; username: string; role: string } | null;
  setTokens: (access: string) => void;
  setUser: (user: AuthState["user"]) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
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
        if (state.accessToken || getAccessToken()) return;
        void refreshAccessToken().then((token) => {
          if (token) state?.setTokens(token);
        });
      },
    },
  ),
);
