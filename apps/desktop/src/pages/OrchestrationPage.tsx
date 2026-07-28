import { useEffect } from 'react';
import { Table, Button, Space, Tag, Typography, Modal } from 'antd';
import { PlayCircleOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Task } from '../types';
import { useListTasks, useRunTask } from '../hooks/useOrchestration';
import { formatTime } from '../utils/formatters';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function OrchestrationPage() {
  useEffect(() => { logger.logPageInit('OrchestrationPage'); }, []);

  const companyId = '';
  const { data: tasks, isLoading } = useListTasks(companyId);
  const runMutation = useRunTask();

  const handleRun = (taskId: string) => {
    Modal.confirm({
      title: '确认运行',
      content: '确定要运行此任务吗？',
      onOk: async () => {
        try {
          logger.info('OrchestrationPage', 'run_start', { taskId });
          await runMutation.mutateAsync(taskId);
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          logger.error('OrchestrationPage', 'run_failed', msg, { taskId });
        }
      },
    });
  };

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
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />}>详情</Button>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleRun(record.id)}>运行</Button>
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
