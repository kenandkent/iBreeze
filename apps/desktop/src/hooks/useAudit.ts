import { useQuery } from '@tanstack/react-query';
import type { AuditLogEntry } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

interface AuditLogListParams {
  start_time?: string;
  end_time?: string;
  event_type?: string;
  cursor?: string;
  limit?: number;
}

export function useListAuditLogs(_params: AuditLogListParams = {}) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.auditLogList(ctx),
    queryFn: async (): Promise<AuditLogEntry[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<AuditLogEntry[]>('event.replay', { limit: 50 });
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
      return createRpcRequest<AuditLogEntry[]>('event.replay', { limit: 1000 });
    },
    isPending: false,
  };
}
