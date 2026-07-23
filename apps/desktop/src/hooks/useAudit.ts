import { useQuery } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { AuditLogEntry } from '../types';

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
      return invoke<AuditLogEntry[]>('list_companies');
    },
  });
}

export function useExportAuditLogs() {
  return {
    mutateAsync: async (_params: AuditLogListParams) => {
      return invoke<AuditLogEntry[]>('list_companies');
    },
    isPending: false,
  };
}
