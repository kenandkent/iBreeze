import { describe, it, expect, vi } from 'vitest';

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

import { rpcCall, checkSidecarHealth } from './rpcClient';

const SIDECAR_NOT_RUNNING = 'SIDECAR_NOT_RUNNING';

describe('rpcClient', () => {
  it('rpcCall sends request and returns result', async () => {
    mockInvoke.mockResolvedValueOnce({ status: 'healthy' });
    const result = await rpcCall<{ status: string }>('sys.health');
    expect(result).toEqual({ status: 'healthy' });
    expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
      method: 'sys.health',
    }));
  });

  it('rpcCall returns null for null result', async () => {
    mockInvoke.mockResolvedValueOnce(null);
    const result = await rpcCall('sys.health');
    expect(result).toBeNull();
  });

  it('rpcCall sends params as JSON string', async () => {
    mockInvoke.mockResolvedValueOnce([]);
    await rpcCall('task.list', { company_id: 'comp-1' });
    expect(mockInvoke).toHaveBeenCalledWith('sys_rpc_call', expect.objectContaining({
      params: '{"company_id":"comp-1"}',
    }));
  });

  it('checkSidecarHealth returns true when healthy', async () => {
    mockInvoke.mockResolvedValueOnce({ status: 'healthy' });
    const healthy = await checkSidecarHealth();
    expect(healthy).toBe(true);
  });

  it('checkSidecarHealth returns false when not running', async () => {
    mockInvoke.mockRejectedValueOnce(new Error(SIDECAR_NOT_RUNNING));
    const healthy = await checkSidecarHealth();
    expect(healthy).toBe(false);
  });

  it('checkSidecarHealth returns false on other errors', async () => {
    mockInvoke.mockRejectedValueOnce(new Error('connection refused'));
    const healthy = await checkSidecarHealth();
    expect(healthy).toBe(false);
  });

  it('rpcCall throws SIDECAR_NOT_RUNNING error', async () => {
    mockInvoke.mockRejectedValueOnce(new Error(SIDECAR_NOT_RUNNING));
    await expect(rpcCall('sys.health')).rejects.toThrow(SIDECAR_NOT_RUNNING);
  });

  it('rpcCall throws SIDECAR_NOT_RUNNING when error contains Failed to connect', async () => {
    mockInvoke.mockRejectedValueOnce('Failed to connect to sidecar');
    await expect(rpcCall('sys.health')).rejects.toThrow('SIDECAR_NOT_RUNNING');
  });

  it('rpcCall throws SIDECAR_NOT_RUNNING when error contains Connection refused', async () => {
    mockInvoke.mockRejectedValueOnce('Connection refused');
    await expect(rpcCall('sys.health')).rejects.toThrow('SIDECAR_NOT_RUNNING');
  });

  it('rpcCall re-throws non-connection errors directly', async () => {
    mockInvoke.mockRejectedValueOnce('some other error');
    await expect(rpcCall('sys.health')).rejects.toBe('some other error');
  });
});
