import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../../src/stores/authStore';

describe('useAuthStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      profileOpened: false,
      profileDirectoryId: null,
      backendOrigin: null,
      appUserId: null,
      maskedIdentifier: null,
      mode: null,
      catalogReleaseSequence: null,
    });
  });

  it('has correct initial state', () => {
    const state = useAuthStore.getState();
    expect(state.profileOpened).toBe(false);
    expect(state.profileDirectoryId).toBeNull();
    expect(state.backendOrigin).toBeNull();
    expect(state.appUserId).toBeNull();
    expect(state.maskedIdentifier).toBeNull();
    expect(state.mode).toBeNull();
    expect(state.catalogReleaseSequence).toBeNull();
  });

  it('setBackendOrigin updates backendOrigin', () => {
    useAuthStore.getState().setBackendOrigin('https://example.com');
    expect(useAuthStore.getState().backendOrigin).toBe('https://example.com');
  });

  it('setBackendOrigin can set null', () => {
    useAuthStore.getState().setBackendOrigin('https://example.com');
    useAuthStore.getState().setBackendOrigin(null);
    expect(useAuthStore.getState().backendOrigin).toBeNull();
  });

  it('setAppUserId updates appUserId', () => {
    useAuthStore.getState().setAppUserId('user-123');
    expect(useAuthStore.getState().appUserId).toBe('user-123');
  });

  it('openProfile sets all profile fields', () => {
    useAuthStore.getState().openProfile({
      profileDirectoryId: 'dir-1',
      maskedIdentifier: 'u***@example.com',
      mode: 'online',
      catalogReleaseSequence: 42,
    });
    const state = useAuthStore.getState();
    expect(state.profileOpened).toBe(true);
    expect(state.profileDirectoryId).toBe('dir-1');
    expect(state.maskedIdentifier).toBe('u***@example.com');
    expect(state.mode).toBe('online');
    expect(state.catalogReleaseSequence).toBe(42);
  });

  it('openProfile with offline mode', () => {
    useAuthStore.getState().openProfile({
      profileDirectoryId: 'dir-2',
      maskedIdentifier: 'test',
      mode: 'offline',
      catalogReleaseSequence: 1,
    });
    expect(useAuthStore.getState().mode).toBe('offline');
  });

  it('closeProfile resets profile fields', () => {
    useAuthStore.getState().openProfile({
      profileDirectoryId: 'dir-1',
      maskedIdentifier: 'test',
      mode: 'online',
      catalogReleaseSequence: 1,
    });
    useAuthStore.getState().closeProfile();
    const state = useAuthStore.getState();
    expect(state.profileOpened).toBe(false);
    expect(state.profileDirectoryId).toBeNull();
    expect(state.maskedIdentifier).toBeNull();
    expect(state.mode).toBeNull();
    expect(state.catalogReleaseSequence).toBeNull();
  });
});
