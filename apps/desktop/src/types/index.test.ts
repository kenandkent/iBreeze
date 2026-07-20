import { describe, it, expect } from 'vitest';
import type {
  Company, Department, Employee, Task, KnowledgeDocument,
  Skill, ToolBinding, PromptAsset, PromptSegments, PromptVariable,
  Capability, CostPolicy, SkillBinding, EmployeeTemplate, RpcResponse, PageKey,
} from './index';

describe('types', () => {
  it('Company has expected fields', () => {
    const c: Company = { company_id: '1', name: 'Test', status: 'active', version: 1, created_at: '2024-01-01' };
    expect(c.company_id).toBe('1');
  });

  it('Department has expected fields', () => {
    const d: Department = {
      department_id: '1', company_id: 'c1', parent_department_id: null,
      name: 'Eng', description: '', status: 'active', created_at: '2024-01-01',
    };
    expect(d.department_id).toBe('1');
  });

  it('Employee has expected fields', () => {
    const e: Employee = {
      employee_id: '1', company_id: 'c1', department_id: 'd1',
      template_id: 't1', name: 'Bob', role_name: 'dev',
      employee_type: 'ai', status: 'active',
    };
    expect(e.employee_id).toBe('1');
  });

  it('Task has expected fields', () => {
    const t: Task = {
      task_id: '1', company_id: 'c1', title: 'Task', description: '',
      status: 'created', priority: 5, version: 1, created_at: '2024-01-01',
    };
    expect(t.task_id).toBe('1');
  });

  it('KnowledgeDocument has expected fields', () => {
    const k: KnowledgeDocument = {
      document_id: '1', company_id: 'c1', title: 'Doc',
      source_category: 'custom', status: 'active',
    };
    expect(k.document_id).toBe('1');
  });

  it('Skill has expected fields', () => {
    const s: Skill = {
      skill_id: '1', company_scope: 'company', company_id: 'c1',
      name: 'Skill', prompt_asset_id: 'p1', prompt_asset_version: 1,
      tool_bindings: [], knowledge_refs: [], input_schema: {},
      output_schema: {}, checksum: 'abc', version: 1, status: 'draft',
      created_at: '', updated_at: '',
    };
    expect(s.skill_id).toBe('1');
  });

  it('ToolBinding has expected fields', () => {
    const tb: ToolBinding = {
      tool_name: 'search', entrypoint: 'search.py',
      required_permissions: [], timeout: 30,
    };
    expect(tb.tool_name).toBe('search');
  });

  it('PromptAsset has expected fields', () => {
    const pa: PromptAsset = {
      prompt_asset_id: '1', company_scope: 'company', company_id: 'c1',
      name: 'Prompt', segments: {} as PromptSegments, variables: [],
      context_slots: [], checksum: '', version: 1, status: 'draft',
      created_at: '', updated_at: '',
    };
    expect(pa.prompt_asset_id).toBe('1');
  });

  it('PromptSegments has expected fields', () => {
    const ps: PromptSegments = {
      system: '', developer: '', user_template: '',
      tool_instructions: '', output_contract: '',
    };
    expect(ps.system).toBe('');
  });

  it('PromptVariable has expected fields', () => {
    const pv: PromptVariable = {
      name: 'x', type: 'string', required: true, default: '', validator: '',
    };
    expect(pv.name).toBe('x');
  });

  it('Capability has expected fields', () => {
    const cap: Capability = {
      capability_id: '1', company_scope: 'company', company_id: 'c1',
      name: 'Cap', description: '', source_category: 'custom',
      visibility: 'company', cost_policy: {} as CostPolicy,
      skill_bindings: [], checksum: '', version: 1, status: 'draft',
      created_at: '', updated_at: '',
    };
    expect(cap.capability_id).toBe('1');
  });

  it('CostPolicy has expected fields', () => {
    const cp: CostPolicy = {
      default_model_tier: 'free', stability_level: 5,
      worker_upgrade_ceiling: '', on_budget_exceeded: '',
    };
    expect(cp.default_model_tier).toBe('free');
  });

  it('SkillBinding has expected fields', () => {
    const sb: SkillBinding = {
      binding_id: '1', skill_id: 's1', skill_version: 1,
      skill_version_checksum: '', ordinal: 0,
    };
    expect(sb.binding_id).toBe('1');
  });

  it('EmployeeTemplate has expected fields', () => {
    const et: EmployeeTemplate = {
      template_id: '1', template_scope: 'company', company_id: 'c1',
      provider_type: 'openai', provider_id: 'openai', model: 'gpt-4',
      capability_id: 'cap1', capability_version: 1,
      capability_snapshot: {}, default_role: 'dev',
      version: 1, status: 'draft',
    };
    expect(et.template_id).toBe('1');
  });

  it('RpcResponse has expected fields', () => {
    const r: RpcResponse<string> = {
      type: 'response', id: '1', result: 'ok', error: null,
    };
    expect(r.result).toBe('ok');
  });

  it('PageKey includes all pages', () => {
    const pages: PageKey[] = [
      'companies', 'employees', 'tasks', 'knowledge',
      'capabilities', 'skills', 'prompts', 'templates', 'settings',
    ];
    expect(pages).toHaveLength(9);
  });
});
