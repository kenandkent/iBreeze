import { create } from 'zustand';
import type { User } from '../types';

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  user: User | null;
  login: (token: string, refreshToken: string, user: User) => void;
  logout: () => void;
  setTokens: (token: string, refreshToken: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  token: null,
  refreshToken: null,
  isAuthenticated: false,
  user: null,
  login: (token, refreshToken, user) =>
    set({ token, refreshToken, user, isAuthenticated: true }),
  logout: () =>
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false }),
  setTokens: (token, refreshToken) =>
    set({ token, refreshToken }),
  clearAuth: () =>
    set({ token: null, refreshToken: null, user: null, isAuthenticated: false }),
}));
