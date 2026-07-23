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
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,
  login: (token, user) =>
    set({ token, user, isAuthenticated: true }),
  logout: () =>
    set({ token: null, user: null, isAuthenticated: false }),
}));
