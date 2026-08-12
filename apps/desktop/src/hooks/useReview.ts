import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReviewIssue } from '../types';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';
import { logger } from '../utils/logger';
import type { ReviewListissuesResponse } from '../generated/rpc/methods/review.listIssues.response.schema';
import type { ReviewResolveissueRequest } from '../generated/rpc/methods/review.resolveIssue.request.schema';
import type { ReviewResolveissueResponse } from '../generated/rpc/methods/review.resolveIssue.response.schema';

export function useListReviewIssues(companyId: string, reviewId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.reviewIssueList(ctx, companyId, reviewId),
    queryFn: async (): Promise<ReviewIssue[]> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<ReviewListissuesResponse>('review.listIssues', {
          company_id: companyId,
          review_id: reviewId,
        });
        logger.logHookSuccess('useReview', 'review.listIssues', performance.now() - start);
        return result.issues;
      } catch (e) {
        logger.logHookError('useReview', 'review.listIssues', e as Error, performance.now() - start);
        throw e;
      }
    },
    enabled: !!companyId && !!reviewId,
  });
}

export function useResolveReviewIssue() {
  const qc = useQueryClient();
  const ctx = useQueryCtx();
  return useMutation({
    mutationFn: async (params: ReviewResolveissueRequest): Promise<ReviewResolveissueResponse> => {
      const start = performance.now();
      try {
        const result = await createRpcRequest<ReviewResolveissueResponse>('review.resolveIssue', { ...params });
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
