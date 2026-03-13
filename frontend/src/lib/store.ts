import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserProfile, CountryScore } from "./api";

interface AuthState {
  token: string | null;
  user: UserProfile | null;
  setAuth: (token: string, user: UserProfile) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        if (typeof window !== "undefined") localStorage.setItem("doomsday_token", token);
        set({ token, user });
      },
      clearAuth: () => {
        if (typeof window !== "undefined") localStorage.removeItem("doomsday_token");
        set({ token: null, user: null });
      },
    }),
    { name: "doomsday-auth" }
  )
);

interface ClockState {
  worldMap: CountryScore[];
  selectedCountry: string | null;
  setWorldMap: (data: CountryScore[]) => void;
  selectCountry: (iso: string | null) => void;
}

export const useClockStore = create<ClockState>((set) => ({
  worldMap: [],
  selectedCountry: null,
  setWorldMap: (data) => set({ worldMap: data }),
  selectCountry: (iso) => set({ selectedCountry: iso }),
}));
