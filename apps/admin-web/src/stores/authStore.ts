import { create } from 'zustand';

interface AuthUser {
  id: string;
  username: string;
  user_type: 'admin';
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  pwdChangeRequired: boolean;
  login: (token: string, user: AuthUser) => void;
  setPwdChangeRequired: (required: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,
  pwdChangeRequired: false,
  login: (token, user) =>
    set({ token, user, isAuthenticated: true, pwdChangeRequired: false }),
  setPwdChangeRequired: (required) =>
    set({ pwdChangeRequired: required }),
  logout: () =>
    set({ token: null, user: null, isAuthenticated: false, pwdChangeRequired: false }),
}));
