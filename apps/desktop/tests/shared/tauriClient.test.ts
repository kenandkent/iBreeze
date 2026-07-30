import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

const mockInvoke = vi.mocked((await import('@tauri-apps/api/core')).invoke);

const {
  validateOrigin,
  register,
  login,
  changePassword,
  logout,
  listOfflineProfiles,
  openProfile,
  closeProfile,
} = await import('../../src/shared/tauriClient');

describe('tauriClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('validateOrigin', () => {
    it('calls backend_validate_origin with origin', async () => {
      mockInvoke.mockResolvedValue({ valid: true, canonical_origin: 'https://test.com', app_user_id: 'u1' });
      const result = await validateOrigin('https://test.com');
      expect(mockInvoke).toHaveBeenCalledWith('backend_validate_origin', { origin: 'https://test.com' });
      expect(result.valid).toBe(true);
    });
  });

  describe('register', () => {
    it('calls auth_register with email and password', async () => {
      mockInvoke.mockResolvedValue({ app_user_id: 'u1', email: 'a@b.com', masked_identifier: 'a***@b.com' });
      const result = await register({ email: 'a@b.com', password: 'pass' });
      expect(mockInvoke).toHaveBeenCalledWith('auth_register', { email: 'a@b.com', password: 'pass' });
      expect(result.app_user_id).toBe('u1');
    });
  });

  describe('login', () => {
    it('calls auth_login with email and password', async () => {
      mockInvoke.mockResolvedValue({
        status: 'profile_opened',
        profile_directory_id: 'pd1',
        masked_identifier: 'u***@e.com',
        catalog_release_sequence: 1,
      });
      const result = await login({ email: 'u@e.com', password: 'pass' });
      expect(mockInvoke).toHaveBeenCalledWith('auth_login', { email: 'u@e.com', password: 'pass' });
      expect(result.status).toBe('profile_opened');
    });
  });

  describe('changePassword', () => {
    it('calls auth_change_password', async () => {
      mockInvoke.mockResolvedValue({
        status: 'profile_opened',
        profile_directory_id: 'pd1',
        masked_identifier: 'u***',
        catalog_release_sequence: 1,
      });
      const result = await changePassword({ currentPassword: 'old', newPassword: 'new' });
      expect(mockInvoke).toHaveBeenCalledWith('auth_change_password', {
        currentPassword: 'old',
        newPassword: 'new',
      });
      expect(result.profile_directory_id).toBe('pd1');
    });
  });

  describe('logout', () => {
    it('calls auth_logout', async () => {
      mockInvoke.mockResolvedValue({ closed_profile: true, revoked_family: true });
      const result = await logout();
      expect(mockInvoke).toHaveBeenCalledWith('auth_logout');
      expect(result.closed_profile).toBe(true);
    });
  });

  describe('listOfflineProfiles', () => {
    it('calls auth_list_offline_profiles', async () => {
      mockInvoke.mockResolvedValue({ profiles: [] });
      const result = await listOfflineProfiles();
      expect(mockInvoke).toHaveBeenCalledWith('auth_list_offline_profiles');
      expect(result.profiles).toEqual([]);
    });
  });

  describe('openProfile', () => {
    it('calls auth_open_profile with profileDirectoryId', async () => {
      mockInvoke.mockResolvedValue({
        profile_directory_id: 'pd1',
        mode: 'offline',
        catalog_release_sequence: 5,
      });
      const result = await openProfile('pd1');
      expect(mockInvoke).toHaveBeenCalledWith('auth_open_profile', { profileDirectoryId: 'pd1' });
      expect(result.mode).toBe('offline');
    });
  });

  describe('closeProfile', () => {
    it('calls auth_close_profile', async () => {
      mockInvoke.mockResolvedValue({ closed_profile: true });
      const result = await closeProfile();
      expect(mockInvoke).toHaveBeenCalledWith('auth_close_profile');
      expect(result.closed_profile).toBe(true);
    });
  });
});
