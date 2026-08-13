import { useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useParams } from 'react-router-dom';
import { useRoutingDecision, useRoutingDecisions, useRoutingSummary, useRunRoutingOverride } from '../hooks/useRouting';
import { formatNumber, formatTime } from '../utils/formatters';

const { Title } = Typography;

export default function RunRoutingPage() {
  const { companyId, runId } = useParams<{ companyId: string; runId: string }>();
  const summary = useRoutingSummary(companyId!, runId!);
  const decisions = useRoutingDecisions(companyId!, runId!);
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);
  const [override, setOverride] = useState<'force_fixed' | 'force_single' | 'force_ensemble' | 'clear'>('clear');
  const detail = useRoutingDecision(companyId!, selectedDecisionId);
  const overrideMutation = useRunRoutingOverride(companyId!, runId!);
  if (summary.isError || decisions.isError) return <Alert type="error" message="路由观测数据加载失败" />;
  const terminal = ['succeeded', 'failed', 'cancelled', 'timed_out', 'lost'].includes(summary.data?.run_status ?? '');
  const applyOverride = async () => {
    if (!summary.data) return;
    try {
      await overrideMutation.mutateAsync({ override, expectedVersion: summary.data.control.version });
      message.success(override === 'clear' ? '已清除后续 Turn 覆盖' : '已设置后续 Turn 覆盖');
    } catch {
      message.error('覆盖设置失败，请刷新后重试');
    }
  };
  return <div>
    <Title level={3}>Run 路由观测</Title>
    <Card loading={summary.isLoading} title="Summary">
      {summary.data && <>
        <Descriptions column={3} size="small"><Descriptions.Item label="状态">{summary.data.run_status ?? '-'}</Descriptions.Item><Descriptions.Item label="模式">{summary.data.routing_mode ?? '-'}</Descriptions.Item><Descriptions.Item label="阶段">{summary.data.rollout_stage}</Descriptions.Item><Descriptions.Item label="Decision">{summary.data.decision_count}</Descriptions.Item><Descriptions.Item label="Single">{summary.data.single_count}</Descriptions.Item><Descriptions.Item label="Ensemble">{summary.data.ensemble_count}</Descriptions.Item><Descriptions.Item label="Fallback hops">{summary.data.fallback_hops}</Descriptions.Item><Descriptions.Item label="Tokens">{formatNumber(summary.data.total_tokens)}</Descriptions.Item><Descriptions.Item label="P50">{formatNumber(summary.data.p50_latency_ms)} ms</Descriptions.Item><Descriptions.Item label="P95">{formatNumber(summary.data.p95_latency_ms)} ms</Descriptions.Item><Descriptions.Item label="Override">{summary.data.control.override_mode ?? '无'}</Descriptions.Item></Descriptions>
        <Space style={{ marginTop: 12 }}><Select value={override} disabled={terminal || overrideMutation.isPending} onChange={setOverride} options={[{ value: 'clear', label: '不覆盖' }, { value: 'force_fixed', label: '后续 Turn 固定 Anchor' }, { value: 'force_single', label: '后续 Turn 强制单模型' }, { value: 'force_ensemble', label: '后续 Turn 强制 Ensemble' }]} /><Button onClick={applyOverride} disabled={terminal || overrideMutation.isPending}>应用到后续 Turn</Button><Typography.Text type="secondary">覆盖只影响后续 Turn，Run 结束后自动失效。</Typography.Text></Space>
      </>}
    </Card>
    <Card title="Decision" style={{ marginTop: 16 }}><Table loading={decisions.isLoading} rowKey="decision_id" dataSource={decisions.data?.items ?? []} pagination={false} columns={[{ title: 'Turn', dataIndex: 'turn_index' }, { title: 'Tier', dataIndex: 'required_tier' }, { title: 'Confidence', dataIndex: 'confidence', render: (value: number) => formatNumber(value) }, { title: 'Kind', dataIndex: 'selected_kind' }, { title: 'Actual candidates', dataIndex: 'actual_candidate_ids', render: (value: string[]) => value.map(item => <Tag key={item}>{item}</Tag>) }, { title: '状态', dataIndex: 'status' }, { title: '创建时间', dataIndex: 'created_at', render: (value: string) => formatTime(value) }, { title: '详情', render: (_: unknown, row: { decision_id: string }) => <Button size="small" onClick={() => setSelectedDecisionId(row.decision_id)}>查看</Button> }]} /></Card>
    <Drawer title="Decision 详情" open={Boolean(selectedDecisionId)} width={720} onClose={() => setSelectedDecisionId(null)}>
      {detail.data && <Space direction="vertical" style={{ width: '100%' }}>
        <Descriptions size="small" column={2}><Descriptions.Item label="Turn">{detail.data.decision.turn_index}</Descriptions.Item><Descriptions.Item label="状态">{detail.data.decision.status}</Descriptions.Item><Descriptions.Item label="Tier">{detail.data.decision.required_tier}</Descriptions.Item><Descriptions.Item label="置信度">{formatNumber(detail.data.decision.confidence)}</Descriptions.Item></Descriptions>
        <Typography.Text strong>Attempts</Typography.Text>
        <Table size="small" rowKey="attempt_sequence" pagination={false} dataSource={detail.data.attempts} columns={[{ title: '序号', dataIndex: 'attempt_sequence' }, { title: '角色', dataIndex: 'role' }, { title: '候选', dataIndex: 'candidate_id' }, { title: '状态', dataIndex: 'status' }, { title: '错误', dataIndex: 'failure_kind' }, { title: '耗时', dataIndex: 'latency_ms', render: (value: number | null) => `${formatNumber(value)} ms` }, { title: 'Tokens', dataIndex: 'total_tokens', render: (value: number | null) => formatNumber(value) }]} />
        <Typography.Text strong>Outcomes</Typography.Text>
        <Table size="small" rowKey={(row) => `${row.outcome_type}:${row.source_id}`} pagination={false} dataSource={detail.data.outcomes} columns={[{ title: '类型', dataIndex: 'outcome_type' }, { title: '来源', dataIndex: 'source_id' }, { title: '分数', dataIndex: 'score', render: (value: number) => formatNumber(value) }, { title: '标签', dataIndex: 'label' }, { title: '时间', dataIndex: 'occurred_at', render: (value: string) => formatTime(value) }]} />
      </Space>}
    </Drawer>
  </div>;
}
