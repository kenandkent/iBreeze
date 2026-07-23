import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AuditLogEntry } from '../types';

// 列出审计日志
interface AuditLogListParams {
  start_time?: string;
  end_time?: string;
  event_type?: string;
  cursor?: string;
  limit?: number;
}

export function useListAuditLogs(params: AuditLogListParams = {}) {
  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: async (): Promise<{ data: AuditLogEntry[]; total: number; next_cursor?: string }> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC audit.list
      return { data: [], total: 0 };
    },
  });
}

// 导出审计日志
export function useExportAuditLogs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: AuditLogListParams) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC audit.export
      const { data } = await queryClient.fetchQuery({
        queryKey: ['audit-logs', params],
        queryFn: async () => ({ data: [] as AuditLogEntry[], total: 0, next_cursor: undefined }),
      });
      return data;
    },
  });
}
