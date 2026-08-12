import { useEffect } from 'react';
import { Table, Button, Space, Tag, Typography } from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Task } from '../types';
import { useListTasks } from '../hooks/useOrchestration';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function OrchestrationPage() {
  useEffect(() => { logger.logPageInit('OrchestrationPage'); }, []);

  const companyId = '';
  const { data: tasks, isLoading } = useListTasks(companyId);
  const columns: ColumnsType<Task> = [
    { title: '任务', dataIndex: 'id', key: 'id' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'completed' ? 'green' : 'blue'}>{s}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => formatTime(v),
    },
    {
      title: '操作',
      key: 'actions',
      render: () => (
        <Space>
          <Button size="small" icon={<EyeOutlined />}>详情</Button>
          <Button size="small" disabled title="请先在任务详情完成计划确认">运行</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>任务编排</Title>
      </div>
      <Table columns={columns} dataSource={tasks ?? []} rowKey="id" loading={isLoading} />
    </div>
  );
}
