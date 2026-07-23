import { useState } from 'react';
import { Table, Select, Input, DatePicker, Button, Tag, Space, Card } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useListAuditLogs } from '../hooks/useAuditLogs';

const EVENT_TYPES = [
  'auth.login', 'auth.logout', 'auth.refresh',
  'user.create', 'user.update', 'user.delete', 'user.reset_password', 'user.revoke_sessions',
  'catalog.agent.create', 'catalog.agent.update', 'catalog.agent.delete', 'catalog.agent.validate',
  'catalog.model.create', 'catalog.model.update', 'catalog.model.delete', 'catalog.model.validate',
  'catalog.release.create', 'catalog.release.publish',
  'catalog.emergency_disable',
];

const EVENT_COLOR: Record<string, string> = {
  'auth.login': 'green',
  'auth.logout': 'default',
  'auth.refresh': 'blue',
  'user.create': 'blue',
  'user.update': 'orange',
  'user.delete': 'red',
  'user.reset_password': 'orange',
  'user.revoke_sessions': 'orange',
};

export default function AdminAuditLogPage() {
  const [filters, setFilters] = useState<{
    event_type?: string;
    actor_id?: string;
    start_date?: string;
    end_date?: string;
  }>({});

  const { data, isLoading } = useListAuditLogs(filters);

  const logs = data?.data ?? [];

  const columns = [
    {
      title: '事件类型', dataIndex: 'event_type', key: 'event_type',
      render: (type: string) => <Tag color={EVENT_COLOR[type] ?? 'default'}>{type}</Tag>,
    },
    { title: '操作者', dataIndex: 'actor_id', key: 'actor_id' },
    { title: '资源类型', dataIndex: 'resource_type', key: 'resource_type' },
    { title: '资源 ID', dataIndex: 'resource_id', key: 'resource_id' },
    {
      title: '详情', dataIndex: 'detail', key: 'detail',
      render: (detail: Record<string, unknown>) => (
        <pre style={{ margin: 0, fontSize: 12, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {JSON.stringify(detail)}
        </pre>
      ),
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at' },
  ];

  const handleExport = () => {
    const csv = [
      columns.map((c) => c.title).join(','),
      ...logs.map((log) =>
        [log.event_type, log.actor_id, log.resource_type, log.resource_id, JSON.stringify(log.detail), log.created_at].join(',')
      ),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>审计日志</h2>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>导出 CSV</Button>
      </div>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            allowClear
            placeholder="事件类型"
            style={{ width: 200 }}
            onChange={(v) => setFilters((f) => ({ ...f, event_type: v }))}
            options={EVENT_TYPES.map((t) => ({ label: t, value: t }))}
          />
          <Input
            placeholder="操作者 ID"
            allowClear
            onChange={(e) => setFilters((f) => ({ ...f, actor_id: e.target.value || undefined }))}
            style={{ width: 200 }}
          />
          <DatePicker.RangePicker
            onChange={(dates) => {
              setFilters((f) => ({
                ...f,
                start_date: dates?.[0]?.toISOString(),
                end_date: dates?.[1]?.toISOString(),
              }));
            }}
          />
        </Space>
      </Card>
      <Table dataSource={logs} columns={columns} rowKey="id" loading={isLoading} />
    </div>
  );
}
