export interface Company {
  id: string;
  name: string;
  industry?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  company_id: string;
  name: string;
  parent_id?: string;
  status: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface Staff {
  id: string;
  department_id: string;
  name: string;
  role: string;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  company_id: string;
  staff_id: string;
  title?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface Task {
  id: string;
  conversation_id?: string;
  company_id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  assignee_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: string;
  name: string;
  model: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  version: string;
  description?: string;
  category: string;
  is_active: boolean;
}

export interface Artifact {
  id: string;
  workspace_id: string;
  name: string;
  artifact_type: string;
  content?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Review {
  id: string;
  artifact_id: string;
  reviewer_id: string;
  status: string;
  comments?: string;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: string;
  user_type: 'admin' | 'app_user';
  email: string;
  display_name: string;
  status: 'active' | 'disabled';
}

export interface AuthResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_type: string;
  user_id: string;
  display_name?: string;
  pwd_change_required: boolean;
}

export interface Profile {
  id: string;
  name: string;
  backend_origin: string;
  masked_identifier: string;
}

export interface KnowledgeEntry {
  id: string;
  title: string;
  content: string;
  type: 'FAQ' | 'DOC' | 'URL';
  content_hash: string;
  tags: string[];
  status: 'active' | 'archived';
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMember {
  id: string;
  user_id: string;
  role: 'owner' | 'admin' | 'member';
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description?: string;
  owner_id: string;
  status: string;
  members: WorkspaceMember[];
  created_at: string;
  updated_at: string;
}

export interface OrchestrationNode {
  id: string;
  type: string;
  name: string;
  config: Record<string, unknown>;
  position_x: number;
  position_y: number;
}

export interface OrchestrationEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  source_port: string;
  target_port: string;
}

export interface Orchestration {
  id: string;
  name: string;
  description?: string;
  version: number;
  status: string;
  nodes: OrchestrationNode[];
  edges: OrchestrationEdge[];
  created_at: string;
  updated_at: string;
}

export interface OrchestrationRun {
  id: string;
  orchestration_id: string;
  status: 'running' | 'success' | 'failed';
  started_at: string;
  finished_at?: string;
  error_message?: string;
  result?: unknown;
}

export interface AgentInfo {
  id: string;
  agent_type: string;
  status: 'running' | 'stopped' | 'error';
  name: string;
  description?: string;
}

export interface AuditLogEntry {
  id: string;
  event_type: string;
  actor_id: string;
  resource_type: string;
  resource_id: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface DashboardStats {
  total_companies: number;
  total_conversations: number;
  total_knowledge_entries: number;
  total_workspaces: number;
  active_agents: number;
  recent_activity: AuditLogEntry[];
}

export interface PaginatedResponse<T> {
  data: T[];
  next_cursor?: string;
  total: number;
}

// Task hierarchy types
export interface CompanyTask {
  id: string;
  company_id: string;
  title: string;
  description: string;
  status: 'pending' | 'planned' | 'in_progress' | 'review' | 'completed' | 'failed' | 'cancelled';
  priority: 'low' | 'normal' | 'high' | 'urgent';
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DepartmentTask {
  id: string;
  company_id: string;
  department_id: string;
  company_task_id: string;
  title: string;
  description: string;
  status: 'pending' | 'assigned' | 'in_progress' | 'review' | 'completed' | 'failed';
  assigned_employee_id?: string;
  created_at: string;
  updated_at: string;
}

export interface EmployeeTask {
  id: string;
  company_id: string;
  employee_id: string;
  department_task_id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  created_at: string;
}

// Agent Run types
export interface AgentRun {
  id: string;
  company_id: string;
  task_id: string;
  agent_id: string;
  model_id: string;
  purpose: string;
  status: 'queued' | 'starting' | 'running' | 'verifying' | 'succeeded' | 'failed' | 'cancelled' | 'waiting_approval' | 'waiting_resource';
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

// Review types
export interface ReviewAssignment {
  id: string;
  company_id: string;
  artifact_id: string;
  task_id: string;
  reviewer_employee_id: string;
  status: 'assigned' | 'in_progress' | 'completed' | 'cancelled';
  created_at: string;
}

export interface ReviewReport {
  id: string;
  assignment_id: string;
  company_id: string;
  artifact_id: string;
  reviewer_employee_id: string;
  verdict: 'approved' | 'rejected' | 'needs_changes';
  summary: string;
  created_at: string;
}

export interface ReviewIssue {
  id: string;
  company_id: string;
  artifact_id: string;
  review_report_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  description: string;
  file_path?: string;
  line_number?: number;
  status: 'open' | 'resolved' | 'dismissed';
  created_at: string;
}

// Plan types
export interface PlanVersion {
  id: string;
  company_id: string;
  version_number: number;
  status: 'draft' | 'confirmed' | 'rejected' | 'superseded';
  plan_content_json: string;
  created_by: string;
  created_at: string;
}

// Employee types
export interface Employee {
  id: string;
  company_id: string;
  department_id: string;
  display_name: string;
  role: string;
  status: 'active' | 'inactive' | 'retired';
  created_at: string;
  updated_at: string;
}

export interface DepartmentResponsibility {
  id: string;
  department_id: string;
  company_id: string;
  title: string;
  description: string;
  sort_order: number;
  created_at: string;
}

// Profile types
export interface EmployeeBaseProfile {
  id: string;
  employee_id: string;
  company_id: string;
  agent_cli?: string;
  api_model?: string;
  status: 'draft' | 'published' | 'retired';
  created_at: string;
}

export interface EmployeeBaseProfileVersion {
  id: string;
  profile_id: string;
  company_id: string;
  version_number: number;
  agent_cli?: string;
  api_model?: string;
  status: 'draft' | 'published' | 'retired';
  created_at: string;
}

// Workspace types
export interface WorkspaceGrant {
  id: string;
  company_id: string;
  employee_id: string;
  workspace_path: string;
  granted_at: string;
  expires_at?: string;
}

// Event types
export interface RunEvent {
  id: string;
  run_id: string;
  event_type: string;
  payload_json: string;
  sequence: number;
  created_at: string;
}

// Approval types
export interface HumanApproval {
  id: string;
  company_id: string;
  run_id: string;
  tool_name: string;
  parameters_json: string;
  status: 'pending' | 'approved' | 'denied' | 'expired';
  requested_at: string;
  resolved_at?: string;
  created_at: string;
}

// Catalog types
export interface CatalogRelease {
  id: string;
  version: string;
  status: 'draft' | 'published' | 'yanked';
  manifest_json: string;
  created_at: string;
}

export interface EmergencyDisableRelease {
  id: string;
  release_id: string;
  reason: string;
  disabled_at: string;
  expires_at?: string;
}
