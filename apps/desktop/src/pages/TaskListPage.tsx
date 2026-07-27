import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Card, Typography, Table, Tag, Button, Tabs } from 'antd';
import { useListCompanyTasks } from '../hooks/useTask';
import { formatTime } from '../utils/formatters';
import { useNavigate } from 'react-router-dom';
import type { CompanyTask } from '../types';
import { logger } from '../utils/logger';

const { Title } = Typography;

const STATUS_COLORS: Record<string, string> = {
  pending: 'default', planned: 'blue', in_progress: 'processing',
  review: 'warning', completed: 'success', failed: 'error', cancelled: 'default',
};

export default function TaskListPage() {
  const { companyId } = useParams<{ companyId: string }>();
  useEffect(() => { logger.logPageInit('TaskListPage'); }, []);

  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const { data: tasks = [], isLoading } = useListCompanyTasks(companyId!, statusFilter);
  const navigate = useNavigate();

  const columns = [
    { title: '任务标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={STATUS_COLORS[s] || 'default'}>{s}</Tag>,
    },
    { title: '优先级', dataIndex: 'priority', key: 'priority' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => formatTime(v) },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: CompanyTask) => (
        <Button size="small" onClick={() => { logger.logAction('TaskListPage', 'view_task_detail'); navigate(`/tasks/${record.id}`); }}>详情</Button>
      ),
    },
  ];

  return (
    <Card>
      <Title level={3}>任务管理</Title>
      <Tabs
        activeKey={statusFilter || 'all'}
        onChange={(k) => setStatusFilter(k === 'all' ? undefined : k)}
        items={[
          { key: 'all', label: '全部' },
          { key: 'pending', label: '待处理' },
          { key: 'in_progress', label: '进行中' },
          { key: 'review', label: '审查中' },
          { key: 'completed', label: '已完成' },
        ]}
      />
      <Table columns={columns} dataSource={tasks} rowKey="id" loading={isLoading} />
    </Card>
  );
}
