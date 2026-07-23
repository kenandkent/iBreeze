export interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  version: string;
  description?: string;
  category: string;
  compatibility?: Record<string, unknown>;
  is_active: boolean;
  checksum?: string;
}

export interface CatalogRelease {
  id: string;
  version: string;
  manifest: Record<string, unknown>;
  status: string;
  notes?: string;
  published_at?: string;
  created_at: string;
  updated_at: string;
}

export interface AuditLog {
  id: string;
  user_id?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  details?: Record<string, unknown>;
  ip_address?: string;
  created_at: string;
}

export interface AgentCatalogItem {
  id: string;
  key: string;
  catalog_revision: number;
  display_name: string;
  description?: string;
  status: 'draft' | 'validated' | 'published';
  created_at: string;
  updated_at: string;
}

export interface ModelCatalogItem {
  id: string;
  provider_key: string;
  model_key: string;
  display_name: string;
  context_window?: number;
  supports_tools: boolean;
  supports_streaming: boolean;
  supports_vision: boolean;
  status: 'draft' | 'validated' | 'published';
  created_at: string;
  updated_at: string;
}

export interface ProviderCatalogItem {
  id: string;
  display_name: string;
  base_url?: string;
  api_protocol: string;
  status: 'draft' | 'validated' | 'published';
  created_at: string;
  updated_at: string;
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  user_type: 'admin' | 'app_user';
  role: string;
  is_active: boolean;
  protected: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
}

export interface Release {
  id: string;
  version: string;
  manifest: Record<string, unknown>;
  signature: string;
  signing_key_id: string;
  release_sequence: number;
  created_at: string;
}

export interface SkillCatalogItem {
  id: string;
  skill_key: string;
  version: string;
  status: 'draft' | 'validated' | 'published';
  agent_bindings: string[];
  created_at: string;
  updated_at: string;
}

export interface CompatibilityRule {
  id: string;
  agent_key: string;
  model_key: string;
  provider_key?: string;
  platform?: string;
  action: 'allow' | 'deny' | 'fallback';
  fallback_model_key?: string;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
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

export interface SystemSettings {
  token_algorithm: string;
  token_expire_minutes: number;
  refresh_token_expire_days: number;
  log_level: string;
  log_json: boolean;
  sidecar_port: number;
}
