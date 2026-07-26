import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReviewIssue } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';

export function useListReviewIssues(companyId: string, artifactId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.reviewIssueList(ctx, companyId, artifactId),
    queryFn: async (): Promise<ReviewIssue[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<ReviewIssue[]>('review.listIssues', { company_id: companyId, artifact_id: artifactId });
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
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: { company_id: string; issue_id: string; resolution_note?: string }) => {
      const start = performance.now();
      try {
        const result = await createRpcRequest('review.resolveIssue', params);
        logger.logHookSuccess('useReview', 'review.resolveIssue', performance.now() - start);
        return result;
      } catch (e) {
        logger.logHookError('useReview', 'review.resolveIssue', e as Error, performance.now() - start);
        throw e;
      }
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: queryKeys.all(ctx) }); },
  });
}
