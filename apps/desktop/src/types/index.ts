export interface Company {
  id: string;
  name: string;
  industry?: string;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  company_id: string;
  name: string;
  parent_id?: string;
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
  user: User;
  access_token: string;
  refresh_token: string;
  offline_session_ticket: string;
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
