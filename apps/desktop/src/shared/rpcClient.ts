import { invoke } from '@tauri-apps/api/core';
import { isReadOperation } from '../generated/rpc/method_kinds.ts';

export function createRpcRequest<T = unknown>(
  operationId: string,
  params: Record<string, unknown> = {},
  idempotencyKey?: string,
): Promise<T> {
  const localReadOperation = operationId === 'system.health' || operationId === 'updater.verifyLaunch';
  const idempotency_key = isReadOperation(operationId) || localReadOperation
    ? null
    : (idempotencyKey ?? crypto.randomUUID());

  return invoke<T>('rpc_request', {
    method: operationId,
    params,
    idempotency_key,
  });
}

export async function systemHealth(): Promise<{ status: string }> {
  return invoke<{ status: string }>('rpc_request', {
    method: 'system.health',
    params: {},
    idempotency_key: null,
  });
}
