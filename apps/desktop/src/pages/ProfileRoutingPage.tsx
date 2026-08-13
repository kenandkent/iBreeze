import { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { createRpcRequest } from '../shared/rpcClient';
import { logger } from '../utils/logger';
import { useCatalogModels, useCredentials } from '../hooks/useRouting';

const { Title, Paragraph } = Typography;

type RoutingCandidateDraft = {
  candidate_id: string;
  provider_release_id?: string;
  model_binding_id?: string;
  credential_ref?: string;
  eligible_roles?: string[];
  [key: string]: unknown;
};

type RoutingPolicyDraft = {
  schema_version?: number;
  mode?: string;
  anchor_candidate_id?: string;
  candidates?: RoutingCandidateDraft[];
  fallback_order?: string[];
  ensemble?: {
    max_proposers?: number;
    min_successful_proposers?: number;
    proposer_timeout_seconds?: number;
    aggregator_timeout_seconds?: number;
    proposer_max_retries?: number;
  };
  [key: string]: unknown;
};

const emptyPolicy = (): RoutingPolicyDraft => ({
  schema_version: 1,
  mode: 'smart_single',
  anchor_candidate_id: '',
  candidates: [],
  fallback_order: [],
  ensemble: { max_proposers: 3, min_successful_proposers: 2, proposer_timeout_seconds: 60, aggregator_timeout_seconds: 120, proposer_max_retries: 1 },
});

export default function ProfileRoutingPage() {
  const { companyId, profileId } = useParams<{ companyId: string; profileId: string }>();
  const navigate = useNavigate();
  const [profileType, setProfileType] = useState<'agent_cli' | 'api_model'>('api_model');
  const [draftId, setDraftId] = useState(profileId ?? '');
  const [policyText, setPolicyText] = useState('');
  const [issues, setIssues] = useState<Array<{ code: string; json_pointer: string; message: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [versionStatus, setVersionStatus] = useState<'draft' | 'published' | 'retired'>('draft');
  const catalog = useCatalogModels();
  const credentials = useCredentials();
  const parsedPolicy = (() => {
    try { return JSON.parse(policyText) as RoutingPolicyDraft; } catch { return null; }
  })();
  const updatePolicy = (patch: Record<string, unknown>) => {
    if (!parsedPolicy) return;
    setPolicyText(JSON.stringify({ ...parsedPolicy, ...patch }, null, 2));
  };
  const updateCandidate = (candidateId: string, patch: Record<string, unknown>) => {
    if (!parsedPolicy?.candidates) return;
    setPolicyText(JSON.stringify({ ...parsedPolicy, candidates: parsedPolicy.candidates.map(candidate => candidate.candidate_id === candidateId ? { ...candidate, ...patch } : candidate) }, null, 2));
  };
  const readOnly = versionStatus !== 'draft';
  const addCandidate = () => {
    if (readOnly) return;
    const model = catalog.data?.models?.find(item => item.routing_enabled) ?? catalog.data?.models?.[0];
    if (!model) { message.warning('固定 Catalog 尚无可用模型'); return; }
    const candidateId = crypto.randomUUID();
    const candidate: RoutingCandidateDraft = { candidate_id: candidateId, provider_release_id: model.provider_release_id, model_binding_id: model.model_binding_id, credential_ref: '', enabled: true, routing_enabled: Boolean(model.routing_enabled), eligible_roles: ['single', 'fallback'] };
    const next = parsedPolicy ?? emptyPolicy();
    const candidates = [...(next.candidates ?? []), candidate];
    setPolicyText(JSON.stringify({ ...next, anchor_candidate_id: next.anchor_candidate_id || candidateId, candidates, fallback_order: [...(next.fallback_order ?? []), candidateId] }, null, 2));
  };
  const removeCandidate = (candidateId: string) => {
    if (readOnly || !parsedPolicy?.candidates) return;
    const candidates = parsedPolicy.candidates.filter(candidate => candidate.candidate_id !== candidateId);
    const fallbackOrder = (parsedPolicy.fallback_order ?? []).filter(id => id !== candidateId);
    setPolicyText(JSON.stringify({ ...parsedPolicy, candidates, fallback_order: fallbackOrder, anchor_candidate_id: parsedPolicy.anchor_candidate_id === candidateId ? candidates[0]?.candidate_id ?? '' : parsedPolicy.anchor_candidate_id }, null, 2));
  };
  const updateEnsemble = (patch: Record<string, unknown>) => {
    if (!parsedPolicy || readOnly) return;
    setPolicyText(JSON.stringify({ ...parsedPolicy, ensemble: { ...(parsedPolicy.ensemble ?? {}), ...patch } }, null, 2));
  };
  useEffect(() => {
    logger.logPageInit('ProfileRoutingPage');
    let mounted = true;
    (async () => {
      try {
        const profile = await createRpcRequest<Record<string, unknown>>('profile.get', { company_id: companyId, profile_id: profileId });
        if (!mounted || !profile) return;
        const type = profile.profile_type === 'agent_cli' ? 'agent_cli' : 'api_model';
        setProfileType(type);
        const versions = Array.isArray(profile.versions) ? profile.versions.filter((version): version is Record<string, unknown> => Boolean(version && typeof version === 'object')) : [];
        const draft = versions.find(version => version.status === 'draft') ?? versions[0];
        if (draft?.status === 'published' || draft?.status === 'retired') setVersionStatus(draft.status);
        else setVersionStatus('draft');
        if (draft?.id) setDraftId(String(draft.id));
        const rawPolicy = draft?.routing_policy_json;
        if (typeof rawPolicy === 'string' && rawPolicy && rawPolicy !== '{}') setPolicyText(JSON.stringify(JSON.parse(rawPolicy), null, 2));
        else setPolicyText(JSON.stringify(emptyPolicy(), null, 2));
      } catch {
        if (mounted) setIssues([{ code: 'PROFILE_LOAD_FAILED', json_pointer: '/', message: '无法读取 Profile 草稿' }]);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [companyId, profileId]);
  const validate = async () => {
    if (readOnly) { setIssues([]); return true; }
    if (profileType === 'agent_cli') { setIssues([]); return true; }
    let policy: unknown;
    try { policy = JSON.parse(policyText); } catch { setIssues([{ code: 'ROUTING_POLICY_INVALID', json_pointer: '/', message: '路由策略必须是合法 JSON' }]); return false; }
    setLoading(true);
    try {
      const result = await createRpcRequest<{ valid: boolean; issues: Array<{ code: string; json_pointer: string; message: string }> }>('routing.validatePolicy', { company_id: companyId, profile_type: profileType, profile_version_id: draftId, policy });
      setIssues(result.issues ?? []); return result.valid;
    } catch { setIssues([{ code: 'ROUTING_POLICY_INVALID', json_pointer: '/', message: '校验请求失败' }]); return false; } finally { setLoading(false); }
  };
  const save = async () => {
    if (readOnly) { navigate(-1); return; }
    if (!(await validate())) { message.error('路由策略未通过校验'); return; }
    if (profileType === 'agent_cli' || !draftId) { navigate(-1); return; }
    setLoading(true);
    try {
      await createRpcRequest('profile.updateDraft', { company_id: companyId, draft_id: draftId, agent_cli: '', api_model: '', routing_policy: JSON.parse(policyText) });
      message.success('路由策略已保存到 Profile 草稿');
      navigate(-1);
    } catch {
      message.error('路由策略保存失败');
    } finally { setLoading(false); }
  };
  return <Card>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Title level={3}>Profile 路由配置</Title>
      <Paragraph type="secondary">Profile：{profileId}，版本：{draftId || '未找到'}，状态：{versionStatus}{readOnly ? '（只读，请创建新 Draft 后修改）' : ''}</Paragraph>
      <Form layout="vertical" style={{ maxWidth: 900 }}>
        <Form.Item label="Profile 类型"><Select disabled={readOnly} value={profileType} onChange={setProfileType} options={[{ value: 'api_model', label: 'API Model（支持 turn 级路由）' }, { value: 'agent_cli', label: 'CLI Agent（仅任务级多职员协作）' }]} /></Form.Item>
        {profileType === 'agent_cli' ? <Alert type="info" message="CLI Agent 不支持 turn 级智能聚合路由，任务将按公司/部门编排执行。" /> : <>
          <Space wrap>
            <Select disabled={readOnly} style={{ width: 220 }} value={parsedPolicy?.mode} placeholder="路由模式" onChange={mode => updatePolicy({ mode })} options={[{ value: 'fixed', label: 'fixed（固定 Anchor）' }, { value: 'smart_single', label: 'smart_single（单模型）' }, { value: 'selective_ensemble', label: 'selective_ensemble（选择性 Ensemble）' }]} />
            <Select disabled={readOnly} style={{ width: 280 }} value={parsedPolicy?.anchor_candidate_id || undefined} placeholder="Anchor Candidate" onChange={anchor_candidate_id => updatePolicy({ anchor_candidate_id })} options={(parsedPolicy?.candidates ?? []).map(candidate => ({ value: candidate.candidate_id, label: String(candidate.candidate_id) }))} />
            <Button disabled={readOnly} onClick={addCandidate}>添加 Candidate</Button>
          </Space>
          {parsedPolicy?.mode !== 'fixed' && <Space wrap>
            <Select disabled={readOnly} mode="multiple" style={{ minWidth: 300 }} value={parsedPolicy?.fallback_order ?? []} onChange={(fallback_order: string[]) => updatePolicy({ fallback_order })} options={(parsedPolicy?.candidates ?? []).map(candidate => ({ value: candidate.candidate_id, label: String(candidate.candidate_id) }))} placeholder="Fallback 顺序" />
            <InputNumber disabled={readOnly} min={2} max={4} value={parsedPolicy?.ensemble?.max_proposers} onChange={value => updateEnsemble({ max_proposers: value ?? 2 })} addonBefore="Max proposers" />
            <InputNumber disabled={readOnly} min={1} max={4} value={parsedPolicy?.ensemble?.min_successful_proposers} onChange={value => updateEnsemble({ min_successful_proposers: value ?? 1 })} addonBefore="Quorum" />
            <InputNumber disabled={readOnly} min={10} max={300} value={parsedPolicy?.ensemble?.proposer_timeout_seconds} onChange={value => updateEnsemble({ proposer_timeout_seconds: value ?? 60 })} addonBefore="Proposer s" />
            <InputNumber disabled={readOnly} min={10} max={480} value={parsedPolicy?.ensemble?.aggregator_timeout_seconds} onChange={value => updateEnsemble({ aggregator_timeout_seconds: value ?? 120 })} addonBefore="Aggregator s" />
            <InputNumber disabled={readOnly} min={0} max={2} value={parsedPolicy?.ensemble?.proposer_max_retries} onChange={value => updateEnsemble({ proposer_max_retries: value ?? 0 })} addonBefore="Retries" />
          </Space>}
          {Array.isArray(parsedPolicy?.candidates) && <Table size="small" pagination={false} rowKey="candidate_id" dataSource={parsedPolicy.candidates} style={{ margin: '12px 0' }} columns={[
            { title: 'Candidate', dataIndex: 'candidate_id' },
            { title: 'Model Binding', dataIndex: 'model_binding_id', render: (value: string, row: RoutingCandidateDraft) => <Select disabled={readOnly} style={{ minWidth: 260 }} value={value} onChange={(model_binding_id: string) => { const model = (catalog.data?.models ?? []).find(item => item.model_binding_id === model_binding_id); updateCandidate(row.candidate_id, { model_binding_id, provider_release_id: model?.provider_release_id ?? row.provider_release_id, routing_enabled: model?.routing_enabled ?? row.routing_enabled }); }} options={(catalog.data?.models ?? []).filter(model => model.routing_enabled).map(model => ({ value: model.model_binding_id, label: `${model.provider} · ${model.name}` }))} /> },
            { title: 'Credential', dataIndex: 'credential_ref', render: (value: string, row: RoutingCandidateDraft) => <Select disabled={readOnly} style={{ minWidth: 220 }} value={value || undefined} onChange={(credential_ref: string) => updateCandidate(row.candidate_id, { credential_ref })} options={(credentials.data?.items ?? []).filter(item => item.state === 'ready' && item.provider_release_id === row.provider_release_id).map(item => ({ value: item.credential_ref, label: `${item.label} · ${item.credential_ref.slice(-8)}` }))} /> },
            { title: 'Roles', dataIndex: 'eligible_roles', render: (value: string[], row: RoutingCandidateDraft) => <Select disabled={readOnly} mode="multiple" style={{ minWidth: 240 }} value={value} onChange={(eligible_roles: string[]) => updateCandidate(row.candidate_id, { eligible_roles })} options={['single', 'proposer', 'aggregator', 'fallback'].map(role => ({ value: role, label: role }))} /> },
            { title: '操作', render: (_: unknown, row: RoutingCandidateDraft) => <Button disabled={readOnly} danger size="small" onClick={() => removeCandidate(row.candidate_id)}>移除</Button> },
          ]} />}
          <Form.Item label="Routing Policy 规范化预览"><Input.TextArea readOnly value={policyText} rows={18} /></Form.Item>
          <Alert type="warning" message="Candidate、Credential 和 Model Binding 只能从固定 Catalog Release 与已 Probe 的 Credential 下拉选择；页面不会把自由文本 ID 发送给 Provider。" />
        </>}
        {issues.length > 0 && <Alert type="error" message="策略存在问题" description={<Space direction="vertical">{issues.map(issue => <Tag color="red" key={`${issue.code}:${issue.json_pointer}`}>{issue.code} {issue.json_pointer}: {issue.message}</Tag>)}</Space>} />}
        <Space><Button onClick={() => navigate(-1)}>返回</Button>{!readOnly && <Button type="primary" loading={loading} onClick={save}>校验并保存</Button>}</Space>
      </Form>
    </Space>
  </Card>;
}
