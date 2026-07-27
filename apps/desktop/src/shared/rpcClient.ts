import { invoke } from '@tauri-apps/api/core';

const READ_OPERATIONS = new Set([
  'company.get',
  'company.list',
  'company.getSettings',
  'department.list',
  'department.get',
  'employee.list',
  'employee.get',
  'task.list',
  'task.get',
  'conversation.list',
  'conversation.getCompany',
  'conversation.listMessages',
  'workspace.get',
  'workspace.list',
  'knowledge.list',
  'knowledge.search',
  'event.replay',
  'review.listIssues',
  'approval.listPending',
  'orchestration.list',
  'orchestration.listRuns',
  'planVersion.list',
]);

export function isReadOperation(operationId: string): boolean {
  return READ_OPERATIONS.has(operationId);
}

export function createRpcRequest<T = unknown>(
  operationId: string,
  params: Record<string, unknown> = {},
  idempotencyKey?: string,
): Promise<T> {
  const idempotency_key = isReadOperation(operationId)
    ? null
    : (idempotencyKey ?? crypto.randomUUID());

  return invoke<T>('rpc_request', {
    method: operationId,
    params,
    idempotency_key,
  });
}

export async function systemHealth(): Promise<{ status: string }> {
  return invoke<{ status: string }>('system_health');
}
