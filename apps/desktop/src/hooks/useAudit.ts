import { useQuery } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { AuditLogEntry } from '../types';
import { logger } from '../utils/logger';

interface AuditLogListParams {
  start_time?: string;
  end_time?: string;
  event_type?: string;
  cursor?: string;
  limit?: number;
}

export function useListAuditLogs(_params: AuditLogListParams = {}) {
  return useQuery({
    queryKey: ['audit-logs'],
    queryFn: async (): Promise<AuditLogEntry[]> => {
      const start = performance.now();
      try {
        const result = await invoke<AuditLogEntry[]>('rpc_request', { method: 'event.replay', params: { limit: 50 } });
        logger.logHookSuccess('useAudit', 'event.replay', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useAudit', 'event.replay', e as Error, performance.now() - start);
        throw e;
      }
    },
  });
}

export function useExportAuditLogs() {
  return {
    mutateAsync: async (_params: AuditLogListParams) => {
      return invoke<AuditLogEntry[]>('rpc_request', { method: 'event.replay', params: { limit: 1000 } });
    },
    isPending: false,
  };
}
