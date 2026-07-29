import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { components } from '../generated/openapi/api';

type AuthUser = components['schemas']['UserInfo'];

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  pwdChangeRequired: boolean;
  login: (token: string, user: AuthUser) => void;
  setPwdChangeRequired: (required: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
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
    }),
    {
      name: 'ibreeze-admin-auth',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        pwdChangeRequired: state.pwdChangeRequired,
      }),
    },
  ),
);
