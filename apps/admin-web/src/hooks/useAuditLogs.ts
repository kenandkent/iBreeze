import { useQuery } from '@tanstack/react-query';
import type { AuditLogEntry } from '../types';

const API_BASE = '/admin/api/v1';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

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
  const url = `${API_BASE}/audit-logs${qs ? `?${qs}` : ''}`;

  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => fetchJson<{ data: AuditLogEntry[] }>(url),
  });
}
