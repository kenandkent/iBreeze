import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoke } from '@tauri-apps/api/core';
import type { ReviewIssue } from '../types';
import { logger } from '../utils/logger';

export function useListReviewIssues(companyId: string, artifactId: string) {
  return useQuery({
    queryKey: ['reviewIssues', companyId, artifactId],
    queryFn: async (): Promise<ReviewIssue[]> => {
      const start = performance.now();
      try {
        const result = await invoke<ReviewIssue[]>('rpc_request', { method: 'review.listIssues', params: { company_id: companyId, artifact_id: artifactId } });
        logger.logHookSuccess('useReview', 'review.listIssues', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useReview', 'review.listIssues', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!artifactId,
  });
}

export function useResolveReviewIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { company_id: string; issue_id: string; resolution_note?: string }) => {
      const start = performance.now();
      try {
        const result = await invoke('rpc_request', { method: 'review.resolveIssue', params });
        logger.logHookSuccess('useReview', 'review.resolveIssue', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useReview', 'review.resolveIssue', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['reviewIssues'] }); },
  });
}
