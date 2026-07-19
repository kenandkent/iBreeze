import { invoke } from '@tauri-apps/api/core';

export async function rpcCall<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  console.log(`[iBreeze] rpcCall: ${method}`, params);
  try {
    const result = await invoke<T>('sys_rpc_call', { method, params: JSON.stringify(params) });
    console.log(`[iBreeze] rpcCall success: ${method}`, result);
    return result;
  } catch (e) {
    const msg = String(e);
    console.error(`[iBreeze] rpcCall error: ${method}`, msg);
    if (msg.includes('Failed to connect') || msg.includes('Connection refused')) {
      throw new Error('SIDECAR_NOT_RUNNING');
    }
    throw e;
  }
}

export async function checkSidecarHealth(): Promise<boolean> {
  try {
    console.log('[iBreeze] checkSidecarHealth');
    await invoke('sys_health');
    console.log('[iBreeze] checkSidecarHealth: OK');
    return true;
  } catch (e) {
    console.error('[iBreeze] checkSidecarHealth failed:', e);
    return false;
  }
}
