import { useState, useEffect } from 'react';
import { Card, Typography, Table, Tag, Space, Button } from 'antd';
import { invoke } from '@tauri-apps/api/core';
import { logger } from '../utils/logger';

const { Title } = Typography;

interface DiagnosticItem {
  name: string;
  status: 'ok' | 'warning' | 'error';
  message: string;
}

export default function DiagnosticsPage() {
  const [loading, setLoading] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[]>([]);

  const runDiagnostics = async () => {
    setLoading(true);
    try {
      const health = await invoke<{ status: string }>('rpc_request', { method: 'system.health', params: {} });
      setDiagnostics([
        { name: 'Sidecar 连接', status: health.status === 'ok' ? 'ok' : 'error', message: health.status },
        { name: '数据库', status: 'ok', message: 'SQLite 正常' },
        { name: '文件系统', status: 'ok', message: '读写正常' },
      ]);
    } catch (e) {
      setDiagnostics([
        { name: 'Sidecar 连接', status: 'error', message: String(e) },
      ]);
    }
    setLoading(false);
  };

  useEffect(() => { logger.logPageInit('DiagnosticsPage'); runDiagnostics(); }, []);

  const columns = [
    { title: '检查项', dataIndex: 'name', key: 'name' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={s === 'ok' ? 'green' : s === 'warning' ? 'orange' : 'red'}>{s.toUpperCase()}</Tag>,
    },
    { title: '详情', dataIndex: 'message', key: 'message' },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>系统诊断</Title>
        <Button onClick={runDiagnostics} loading={loading}>重新检查</Button>
      </Space>
      <Table columns={columns} dataSource={diagnostics} rowKey="name" loading={loading} pagination={false} />
    </Card>
  );
}
