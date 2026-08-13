import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../test-utils';
import { useListAuditLogs } from './useAuditLogs';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');

function makeWrapper() {
  const qc = createTestQueryClient();
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe('useListAuditLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiGet.mockResolvedValue({ items: [] });
  });

  it('calls apiGet with the bare /audit-logs path when no params are given', async () => {
    const { result } = renderHook(() => useListAuditLogs(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiGet).toHaveBeenCalledTimes(1);
    expect(mockApiGet).toHaveBeenCalledWith('/audit-logs');
  });

  it('encodes all params into the query string', async () => {
    const params = {
      event_type: 'auth.login',
      actor_id: 'u9',
      resource_type: 'session',
      start_date: '2024-01-01T00:00:00Z',
      end_date: '2024-01-02T00:00:00Z',
    };
    const { result } = renderHook(() => useListAuditLogs(params), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const url = mockApiGet.mock.calls[0][0] as string;
    expect(url.startsWith('/audit-logs?')).toBe(true);
    for (const [key, value] of Object.entries(params)) {
      expect(url).toContain(`${key}=${encodeURIComponent(value)}`);
    }
  });

  it('appends a query string when only event_type is given', async () => {
    const { result } = renderHook(() => useListAuditLogs({ event_type: 'user.create' }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiGet).toHaveBeenCalledWith('/audit-logs?event_type=user.create');
  });
});
