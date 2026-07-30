import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

const mockInvoke = vi.mocked((await import('@tauri-apps/api/core')).invoke);

const { createRpcRequest, systemHealth } = await import('../src/shared/rpcClient');
const { isReadOperation } = await import('../src/generated/rpc/method_kinds.ts');

describe('isReadOperation', () => {
  it('returns true for get operations', () => {
    expect(isReadOperation('company.get')).toBe(true);
    expect(isReadOperation('task.get')).toBe(true);
    expect(isReadOperation('workspace.get')).toBe(true);
  });

  it('returns true for list operations', () => {
    expect(isReadOperation('company.list')).toBe(true);
    expect(isReadOperation('department.list')).toBe(true);
    expect(isReadOperation('knowledge.list')).toBe(true);
  });

  it('returns true for search and run operations', () => {
    expect(isReadOperation('knowledge.search')).toBe(true);
    expect(isReadOperation('run.listEvents')).toBe(true);
  });

  it('returns false for write operations', () => {
    expect(isReadOperation('company.create')).toBe(false);
    expect(isReadOperation('company.update')).toBe(false);
    expect(isReadOperation('company.archive')).toBe(false);
    expect(isReadOperation('task.confirmPlan')).toBe(false);
    expect(isReadOperation('conversation.archive')).toBe(false);
  });
});

describe('createRpcRequest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes null idempotency_key for read operations', async () => {
    mockInvoke.mockResolvedValue({ id: '1', name: 'test' });
    await createRpcRequest('company.get', { id: '1' });
    expect(mockInvoke).toHaveBeenCalledWith('rpc_request', {
      method: 'company.get',
      params: { id: '1' },
      idempotency_key: null,
    });
  });

  it('generates a UUID idempotency_key for write operations', async () => {
    mockInvoke.mockResolvedValue({ id: '1' });
    await createRpcRequest('company.create', { name: 'test' });
    const call = mockInvoke.mock.calls[0]?.[1] as Record<string, unknown>;
    expect(call).toBeDefined();
    expect(call.idempotency_key).toEqual(expect.any(String));
    expect(call.idempotency_key).not.toBeNull();
    expect(String(call.idempotency_key)).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    );
  });

  it('accepts an explicit idempotency_key override', async () => {
    mockInvoke.mockResolvedValue({});
    const explicitKey = 'my-custom-key';
    await createRpcRequest('company.update', { id: '1' }, explicitKey);
    expect(mockInvoke).toHaveBeenCalledWith('rpc_request', {
      method: 'company.update',
      params: { id: '1' },
      idempotency_key: explicitKey,
    });
  });

  it('does not use idempotency_key override for reads', async () => {
    mockInvoke.mockResolvedValue({});
    await createRpcRequest('company.list', {}, 'should-be-ignored');
    expect(mockInvoke).toHaveBeenCalledWith('rpc_request', {
      method: 'company.list',
      params: {},
      idempotency_key: null,
    });
  });
});

describe('systemHealth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls system_health invoke directly', async () => {
    mockInvoke.mockResolvedValue({ status: 'ok' });
    const result = await systemHealth();
    expect(mockInvoke).toHaveBeenCalledWith('system_health');
    expect(result).toEqual({ status: 'ok' });
  });
});
