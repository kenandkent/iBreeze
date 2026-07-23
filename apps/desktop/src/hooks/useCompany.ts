import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Company } from '../types';

// 企业查询参数
interface CompanyListParams {
  search?: string;
  status?: string;
  cursor?: string;
  limit?: number;
}

// 列出企业
export function useListCompanies(params: CompanyListParams = {}) {
  return useQuery({
    queryKey: ['companies', params],
    queryFn: async (): Promise<{ data: Company[]; total: number; next_cursor?: string }> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC company.list
      return { data: [], total: 0 };
    },
  });
}

// 获取单个企业详情
export function useGetCompany(id: string) {
  return useQuery({
    queryKey: ['companies', id],
    queryFn: async (): Promise<Company> => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC company.get
      throw new Error('Not implemented');
    },
    enabled: !!id,
  });
}

// 创建企业
export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { name: string; industry?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC company.create
      return { id: crypto.randomUUID(), ...data, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}

// 更新企业
export function useUpdateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: { id: string; name?: string; industry?: string }) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC company.update
      return { ...data, updated_at: new Date().toISOString() };
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      queryClient.invalidateQueries({ queryKey: ['companies', variables.id] });
    },
  });
}

// 删除企业
export function useDeleteCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (_id: string) => {
      // TODO: 通过 Tauri IPC 调用 Sidecar RPC company.delete
      return { success: true };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });
}
