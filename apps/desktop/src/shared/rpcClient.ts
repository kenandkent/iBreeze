import { invoke } from '@tauri-apps/api/core';

const READ_OPERATIONS = new Set([
  'approval.listPending',
  'artifact.getSnapshot',
  'artifact.list',
  'backup.list',
  'catalog.getActiveRelease',
  'catalog.listAgents',
  'catalog.listModels',
  'catalog.listSkills',
  'company.get',
  'company.list',
  'conversation.getCompany',
  'conversation.getDepartment',
  'conversation.list',
  'conversation.listMessages',
  'department.get',
  'department.list',
  'departmentTask.getReport',
  'employee.get',
  'employee.list',
  'knowledge.list',
  'knowledge.search',
  'profile.get',
  'profile.list',
  'review.listIssues',
  'run.get',
  'run.list',
  'run.listEvents',
  'runtime.getStatus',
  'runtime.listAvailableModels',
  'runtime.probeAgent',
  'runtime.probeProvider',
  'settings.get',
  'task.get',
  'task.getEvidence',
  'task.getGraph',
  'task.list',
  'workspace.get',
  'workspace.list',
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
