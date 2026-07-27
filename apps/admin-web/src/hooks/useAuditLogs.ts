import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../utils/apiClient';
import type { AuditLogEntry } from '../types';

export function useListAuditLogs(params?: {
  event_type?: string;
  actor_id?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
}) {
  const searchParams = new URLSearchParams();
  if (params?.event_type) searchParams.set('event_type', params.event_type);
  if (params?.actor_id) searchParams.set('actor_id', params.actor_id);
  if (params?.resource_type) searchParams.set('resource_type', params.resource_type);
  if (params?.start_date) searchParams.set('start_date', params.start_date);
  if (params?.end_date) searchParams.set('end_date', params.end_date);

  const qs = searchParams.toString();
  const url = `/audit-logs${qs ? `?${qs}` : ''}`;

  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => apiGet<{ items: AuditLogEntry[] }>(url),
  });
}
