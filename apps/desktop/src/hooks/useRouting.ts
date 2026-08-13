import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createRpcRequest } from '../shared/rpcClient';
import { queryKeys, useQueryCtx } from '../shared/queryKeys';

export interface RoutingSummary {
  run_id: string;
  run_status?: string;
  routing_mode: string | null;
  rollout_stage: string;
  decision_count: number;
  single_count: number;
  ensemble_count: number;
  fallback_hops: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  actual_models: Array<{ candidate_id: string; provider_release_id: string; model_binding_id: string; attempt_count: number; success_count: number }>;
  control: { override_mode: string | null; version: number };
}

export interface RoutingDecision {
  decision_id: string;
  turn_index: number;
  routing_mode: string;
  required_tier: string;
  confidence: number;
  selected_kind: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  actual_candidate_ids: string[];
}

export interface RoutingDecisionDetail {
  decision: RoutingDecision & {
    company_id: string;
    run_id: string;
    execution_snapshot_id: string;
    classifier_version: string;
    selected_bindings: Array<{ candidate_id: string; role: string }>;
    policy_trail: Array<Record<string, unknown>>;
  };
  attempts: Array<{
    attempt_sequence: number;
    role: string;
    candidate_id: string;
    provider_release_id: string;
    model_binding_id: string;
    status: string;
    failure_kind: string | null;
    http_status: number | null;
    created_at: string;
    accepted_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    latency_ms: number | null;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    candidate_truncated: boolean;
  }>;
  outcomes: Array<{ outcome_type: string; source_id: string; score: number; label: string; occurred_at: string }>;
}

export interface DeploymentHealth {
  provider_release_id: string;
  model_binding_id: string;
  credential_slot: string;
  availability_state: string;
  consecutive_strikes: number;
  benched_until: string | null;
  last_failure_kind: string | null;
  last_failure_at: string | null;
  last_success_at: string | null;
  version: number;
}

export function useRoutingSummary(companyId: string, runId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.routingSummary(ctx, companyId, runId),
    queryFn: () => createRpcRequest<RoutingSummary>('routing.getRunSummary', { company_id: companyId, run_id: runId }),
    enabled: Boolean(companyId && runId),
  });
}

export function useRoutingDecisions(companyId: string, runId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.routingDecisions(ctx, companyId, runId),
    queryFn: () => createRpcRequest<{ items: RoutingDecision[]; next_cursor: string | null }>('routing.listDecisions', { company_id: companyId, run_id: runId, limit: 100 }),
    enabled: Boolean(companyId && runId),
  });
}

export function useRoutingDecision(companyId: string, decisionId: string | null) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: [...queryKeys.all(ctx), companyId, 'routing', 'decision', decisionId] as const,
    queryFn: () => createRpcRequest<RoutingDecisionDetail>('routing.getDecision', { company_id: companyId, decision_id: decisionId }),
    enabled: Boolean(companyId && decisionId),
  });
}

export function useDeploymentHealth(companyId: string, activeOnly = false) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: [...queryKeys.routingHealth(ctx, companyId), activeOnly] as const,
    queryFn: () => createRpcRequest<{ items: DeploymentHealth[]; next_cursor: string | null }>('routing.listDeploymentHealth', { company_id: companyId, active_only: activeOnly, limit: 100 }),
    enabled: Boolean(companyId),
  });
}

export function useClearExpiredHealth(companyId: string) {
  const ctx = useQueryCtx();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => createRpcRequest<{ deleted_count: number }>('routing.clearExpiredHealth', { company_id: companyId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.routingHealth(ctx, companyId) }),
  });
}

export function useRunRoutingOverride(companyId: string, runId: string) {
  const ctx = useQueryCtx();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { override: 'force_fixed' | 'force_single' | 'force_ensemble' | 'clear'; expectedVersion: number }) =>
      createRpcRequest('routing.setRunOverride', { company_id: companyId, run_id: runId, expected_version: input.expectedVersion, override: input.override }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.routingSummary(ctx, companyId, runId) }),
  });
}

export interface CredentialMetadata {
  credential_ref: string;
  label: string;
  provider_release_id: string;
  auth_type: 'bearer' | 'x_api_key';
  state: 'creating' | 'updating' | 'unverified' | 'ready' | 'deleting';
  metadata_version: number;
  active_secret_version: number | null;
}

export interface CatalogModelOption {
  model_id: string;
  name: string;
  provider: string;
  provider_release_id: string;
  model_binding_id: string;
  provider_protocol: string;
  routing_enabled: boolean;
}

export interface ProfileSummary {
  profile_id: string;
  display_name: string;
  status: 'draft' | 'published' | 'retired';
  version: number;
  updated_at: string;
  profile_type: 'agent_cli' | 'api_model';
  current_version_id: string | null;
  current_version_status: 'draft' | 'published' | 'retired';
}

export function useProfiles(companyId: string) {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: [...queryKeys.all(ctx), companyId, 'profiles'] as const,
    queryFn: () => createRpcRequest<{ profiles: ProfileSummary[] }>('profile.list', { company_id: companyId }),
    enabled: Boolean(companyId),
  });
}

export function useCatalogModels() {
  const ctx = useQueryCtx();
  return useQuery({
    queryKey: queryKeys.catalogModels(ctx),
    queryFn: () => createRpcRequest<{ models: CatalogModelOption[] }>('catalog.listModels', {}),
  });
}

export function useCredentials() {
  const ctx = useQueryCtx();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.credentials(ctx),
    queryFn: () => createRpcRequest<{ items: CredentialMetadata[] }>('credential.list', {}),
  });
  const create = useMutation({
    mutationFn: (payload: { label: string; provider_release_id: string; auth_type: 'bearer' | 'x_api_key'; secret: string }) => createRpcRequest<CredentialMetadata>('credential.create', payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.credentials(ctx) }),
  });
  const updateSecret = useMutation({
    mutationFn: (payload: { credential_ref: string; expected_metadata_version: number; secret: string }) => createRpcRequest<CredentialMetadata>('credential.updateSecret', payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.credentials(ctx) }),
  });
  const probe = useMutation({
    mutationFn: (payload: { credential_ref: string; expected_metadata_version: number }) => createRpcRequest('credential.probe', payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.credentials(ctx) }),
  });
  const remove = useMutation({
    mutationFn: (payload: { credential_ref: string; expected_metadata_version: number }) => createRpcRequest('credential.delete', payload),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.credentials(ctx) }),
  });
  return { ...query, create, updateSecret, probe, remove };
}
