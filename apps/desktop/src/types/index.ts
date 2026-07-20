export interface Company {
  company_id: string;
  name: string;
  status: string;
  version: number;
  created_at: string;
}

export interface Department {
  department_id: string;
  company_id: string;
  parent_department_id: string | null;
  name: string;
  description: string;
  status: string;
  created_at: string;
}

export interface Employee {
  employee_id: string;
  company_id: string;
  department_id: string;
  template_id: string;
  name: string;
  role_name: string;
  employee_type: string;
  status: string;
}

export interface Task {
  task_id: string;
  company_id: string;
  title: string;
  description: string;
  status: string;
  priority: number;
  version: number;
  created_at: string;
}

export interface KnowledgeDocument {
  document_id: string;
  company_id: string;
  title: string;
  source_category: string;
  status: string;
}

export interface Skill {
  skill_id: string;
  company_scope: string;
  company_id: string | null;
  name: string;
  prompt_asset_id: string;
  prompt_asset_version: number;
  tool_bindings: ToolBinding[];
  knowledge_refs: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  checksum: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ToolBinding {
  tool_name: string;
  entrypoint: string;
  required_permissions: string[];
  timeout: number;
}

export interface PromptAsset {
  prompt_asset_id: string;
  company_scope: string;
  company_id: string | null;
  name: string;
  segments: PromptSegments;
  variables: PromptVariable[];
  context_slots: string[];
  checksum: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PromptSegments {
  system: string;
  developer: string;
  user_template: string;
  tool_instructions: string;
  output_contract: string;
}

export interface PromptVariable {
  name: string;
  type: string;
  required: boolean;
  default: string;
  validator: string;
}

export interface Capability {
  capability_id: string;
  company_scope: string;
  company_id: string | null;
  name: string;
  description: string;
  source_category: string;
  visibility: string;
  cost_policy: CostPolicy;
  skill_bindings: SkillBinding[];
  checksum: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CostPolicy {
  default_model_tier: string;
  stability_level: number;
  worker_upgrade_ceiling: string;
  on_budget_exceeded: string;
}

export interface SkillBinding {
  binding_id: string;
  skill_id: string;
  skill_version: number;
  skill_version_checksum: string;
  ordinal: number;
}

export interface EmployeeTemplate {
  template_id: string;
  template_scope: string;
  company_id: string | null;
  provider_type: string;
  provider_id: string;
  model: string;
  capability_id: string;
  capability_version: number;
  capability_snapshot: Record<string, unknown>;
  default_role: string;
  version: number;
  status: string;
}

export interface RpcResponse<T> {
  type: string;
  id: string;
  result: T;
  error: string | null;
}

export interface SessionThread {
  thread_id: string;
  company_id: string;
  user_id: string;
  status: string;
  security_context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SessionMessage {
  message_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface Backend {
  backend_id: string;
  name: string;
  type: string;
  provider_id?: string;
  backend_type?: string;
  status: string;
  health: string;
  health_status?: string;
  capacity: number;
  company_id: string;
}

export interface Provider {
  provider_id: string;
  name: string;
  type: string;
  provider_type?: string;
  status: string;
  company_id: string;
  config?: Record<string, unknown>;
}

export interface CliAgentOption {
  agent_id: string;
  display_name: string;
  models: { model: string; display_name: string }[];
}

export interface ProviderModel {
  model_id: string;
  provider_id: string;
  name: string;
  company_id: string;
}

export interface PricingPolicy {
  provider_id: string;
  company_id: string;
  policy: Record<string, unknown>;
}

export interface Grant {
  grant_id: string;
  company_id: string;
  target_type: string;
  target_ref: string;
  permission: string;
  expires_at: string;
  status: string;
  created_at: string;
}

export interface Intervention {
  intervention_id: string;
  company_id: string;
  reason: string;
  target_ref: string;
  status: string;
  created_at: string;
}

export interface AuditEntry {
  audit_id: string;
  audit_type: string;
  company_id: string;
  action: string;
  resource: string;
  result: string;
  created_at: string;
}

export type AuditType = 'acl' | 'org' | 'governance';

export type PageKey =
  | 'companies'
  | 'employees'
  | 'tasks'
  | 'knowledge'
  | 'capabilities'
  | 'skills'
  | 'prompts'
  | 'templates'
  | 'settings'
  | 'session'
  | 'provider'
  | 'grant'
  | 'intervention'
  | 'audit'
  | 'dashboard';
