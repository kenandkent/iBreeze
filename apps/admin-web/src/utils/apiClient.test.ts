import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiError, apiGet, apiPost, apiPatch, apiPut, apiDelete, apiUpload, apiLogin, apiLogout } from './apiClient';
import { useAuthStore } from '../stores/authStore';

vi.mock('../stores/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(),
  },
}));

const mockGetState = vi.mocked(useAuthStore.getState);

function mockFetch(response: { ok: boolean; status: number; json?: unknown; headers?: Record<string, string> }) {
  return vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status,
    json: vi.fn().mockResolvedValue(response.json),
    headers: new Map(Object.entries(response.headers ?? {})),
  });
}

describe('ApiError', () => {
  it('creates error with status and message', () => {
    const err = new ApiError(404, { detail: 'Not found' });
    expect(err.status).toBe(404);
    expect(err.message).toBe('Not found');
    expect(err.name).toBe('ApiError');
    expect(err.code).toBeUndefined();
  });

  it('creates error with code and reference_id', () => {
    const err = new ApiError(400, { code: 'BAD_REQUEST', detail: 'Invalid', reference_id: 'ref-123' });
    expect(err.code).toBe('BAD_REQUEST');
    expect(err.detail).toBe('Invalid');
    expect(err.reference_id).toBe('ref-123');
  });

  it('falls back to title when detail is missing', () => {
    const err = new ApiError(500, { title: 'Server Error' });
    expect(err.message).toBe('Server Error');
  });

  it('falls back to HTTP status message', () => {
    const err = new ApiError(418);
    expect(err.message).toBe('HTTP 418');
  });
});

describe('apiGet', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes GET request with auth header', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: { data: 'hello' } });
    vi.stubGlobal('fetch', fetchMock);

    const result = await apiGet('/test');
    expect(result).toEqual({ data: 'hello' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/api/v1/test',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('throws ApiError on non-ok response', async () => {
    const fetchMock = mockFetch({ ok: false, status: 404, json: { detail: 'Not found' } });
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/missing')).rejects.toThrow(ApiError);
  });
});

describe('apiPost', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes POST request with body', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: { id: '1' } });
    vi.stubGlobal('fetch', fetchMock);

    const result = await apiPost('/items', { name: 'test' });
    expect(result).toEqual({ id: '1' });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.body).toBe(JSON.stringify({ name: 'test' }));
  });

  it('makes POST without body', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await apiPost('/action');
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).toBeUndefined();
  });
});

describe('apiPatch', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes PATCH request with If-Match header', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: { updated: true } });
    vi.stubGlobal('fetch', fetchMock);

    await apiPatch('/items/1', { name: 'new' }, 2);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('PATCH');
    expect(options.headers['If-Match']).toBe('"2"');
  });

  it('makes PATCH without version', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await apiPatch('/items/1', { name: 'new' });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers['If-Match']).toBeUndefined();
  });
});

describe('apiPut', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes PUT request', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await apiPut('/items/1', { name: 'updated' });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('PUT');
  });
});

describe('apiDelete', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes DELETE request', async () => {
    const fetchMock = mockFetch({ ok: true, status: 204, json: undefined });
    vi.stubGlobal('fetch', fetchMock);

    await apiDelete('/items/1');
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('DELETE');
  });

  it('makes DELETE with version header', async () => {
    const fetchMock = mockFetch({ ok: true, status: 204, json: undefined });
    vi.stubGlobal('fetch', fetchMock);

    await apiDelete('/items/1', 3);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers['If-Match']).toBe('"3"');
  });
});

describe('apiUpload', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
  });

  it('makes POST with FormData', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: { uploaded: true } });
    vi.stubGlobal('fetch', fetchMock);

    const formData = new FormData();
    await apiUpload('/upload', formData);
    const [, options] = fetchMock.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.body).toBe(formData);
  });
});

describe('apiLogin', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('returns session data on success', async () => {
    const sessionData = { access_token: 'token', user: { username: 'admin' } };
    const fetchMock = mockFetch({ ok: true, status: 200, json: { data: sessionData } });
    vi.stubGlobal('fetch', fetchMock);

    const result = await apiLogin('admin', 'pass', 'device-1');
    expect(result).toEqual(sessionData);
    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/api/v1/auth/login',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('throws ApiError on login failure', async () => {
    const fetchMock = mockFetch({ ok: false, status: 401, json: { code: 'AUTH_FAILED', detail: 'Bad credentials' } });
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiLogin('admin', 'wrong', 'device-1')).rejects.toThrow(ApiError);
  });
});

describe('apiLogout', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does nothing when no token', async () => {
    mockGetState.mockReturnValue({ token: null } as never);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await apiLogout();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('calls logout endpoint when token exists', async () => {
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
    const fetchMock = mockFetch({ ok: true, status: 200, json: {} });
    vi.stubGlobal('fetch', fetchMock);

    await apiLogout();
    expect(fetchMock).toHaveBeenCalledWith(
      '/admin/api/v1/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('does not throw on logout failure', async () => {
    mockGetState.mockReturnValue({ token: 'test-token' } as never);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')));

    await expect(apiLogout()).resolves.toBeUndefined();
  });
});

describe('apiFetch 401 handling', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('refreshes token on 401 and retries successfully', async () => {
    const loginFn = vi.fn();
    mockGetState
      .mockReturnValueOnce({ token: 'old-token' } as never)
      .mockReturnValueOnce({ token: 'new-token', login: loginFn } as never)
      .mockReturnValueOnce({ token: 'new-token', login: loginFn } as never);

    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 401, json: vi.fn() })
      .mockResolvedValueOnce({ ok: true, status: 200, json: vi.fn().mockResolvedValue({ data: 'access_token', user: {} }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: vi.fn().mockResolvedValue({ result: 'retried' }) });
    vi.stubGlobal('fetch', fetchMock);

    const result = await apiGet('/protected');
    expect(result).toEqual({ result: 'retried' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('logs out on failed refresh after 401', async () => {
    const logoutFn = vi.fn();
    mockGetState
      .mockReturnValue({ token: 'old-token', logout: logoutFn } as never);

    const fetchMock = vi.fn()
      .mockResolvedValue({ ok: false, status: 401, json: vi.fn() });
    vi.stubGlobal('fetch', fetchMock);

    vi.spyOn(window, 'location', 'get').mockReturnValue({ href: '' } as Location);

    await expect(apiGet('/protected')).rejects.toThrow(ApiError);
  });
});
