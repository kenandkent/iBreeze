import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getDeviceId } from './deviceId';

const DEVICE_ID_KEY = 'ibreeze_device_id';
const DEVICE_ID_COOKIE = 'ibreeze_device_id';

describe('getDeviceId', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie.split(';').forEach((c) => {
      const key = c.split('=')[0].trim();
      document.cookie = `${key}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
    });
    localStorage.clear();
  });

  it('generates a new UUID when no cookie or localStorage exists', () => {
    const mockUUID = '123e4567-e89b-12d3-a456-426614174000';
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(mockUUID);

    const id = getDeviceId();
    expect(id).toBe(mockUUID);
    expect(localStorage.getItem(DEVICE_ID_KEY)).toBe(mockUUID);
  });

  it('returns existing cookie value', () => {
    const existingId = 'existing-cookie-id';
    document.cookie = `${DEVICE_ID_COOKIE}=${existingId};path=/`;

    const id = getDeviceId();
    expect(id).toBe(existingId);
  });

  it('falls back to localStorage when no cookie', () => {
    const storedId = 'stored-local-id';
    localStorage.setItem(DEVICE_ID_KEY, storedId);

    const id = getDeviceId();
    expect(id).toBe(storedId);
  });

  it('prefers cookie over localStorage', () => {
    const cookieId = 'cookie-id';
    const storedId = 'stored-id';
    document.cookie = `${DEVICE_ID_COOKIE}=${cookieId};path=/`;
    localStorage.setItem(DEVICE_ID_KEY, storedId);

    const id = getDeviceId();
    expect(id).toBe(cookieId);
  });

  it('sets both cookie and localStorage', () => {
    const mockUUID = 'aaa-bbb-ccc';
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(mockUUID);

    getDeviceId();

    expect(localStorage.getItem(DEVICE_ID_KEY)).toBe(mockUUID);
    expect(document.cookie).toContain(`${DEVICE_ID_COOKIE}=${mockUUID}`);
  });
});
