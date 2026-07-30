import { describe, it, expect, beforeEach } from 'vitest';
import { useProfileStore } from '../../src/stores/profileStore';

describe('useProfileStore', () => {
  beforeEach(() => {
    useProfileStore.setState({ selectedProfileId: null });
  });

  it('has correct initial state', () => {
    expect(useProfileStore.getState().selectedProfileId).toBeNull();
  });

  it('setSelectedProfileId updates selectedProfileId', () => {
    useProfileStore.getState().setSelectedProfileId('profile-1');
    expect(useProfileStore.getState().selectedProfileId).toBe('profile-1');
  });

  it('setSelectedProfileId can set null', () => {
    useProfileStore.getState().setSelectedProfileId('profile-1');
    useProfileStore.getState().setSelectedProfileId(null);
    expect(useProfileStore.getState().selectedProfileId).toBeNull();
  });
});
