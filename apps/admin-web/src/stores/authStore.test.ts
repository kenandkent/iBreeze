import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from './authStore';

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      pwdChangeRequired: false,
    });
    localStorage.clear();
  });

  it('has initial state', () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.pwdChangeRequired).toBe(false);
  });

  it('login sets token, user, and isAuthenticated', () => {
    const mockUser = { username: 'admin', email: 'admin@test.com' } as never;
    useAuthStore.getState().login('test-token', mockUser);

    const state = useAuthStore.getState();
    expect(state.token).toBe('test-token');
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
    expect(state.pwdChangeRequired).toBe(false);
  });

  it('logout clears all state', () => {
    const mockUser = { username: 'admin' } as never;
    useAuthStore.getState().login('test-token', mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.pwdChangeRequired).toBe(false);
  });

  it('setPwdChangeRequired toggles the flag', () => {
    useAuthStore.getState().setPwdChangeRequired(true);
    expect(useAuthStore.getState().pwdChangeRequired).toBe(true);

    useAuthStore.getState().setPwdChangeRequired(false);
    expect(useAuthStore.getState().pwdChangeRequired).toBe(false);
  });
});
