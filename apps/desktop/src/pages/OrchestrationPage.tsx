import { useState } from 'react';
import {
  Table, Button, Space, Tag, Drawer, Form, Input, Typography, Popconfirm, Modal, Table as InnerTable, List,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, PlayCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Orchestration, OrchestrationNode, OrchestrationEdge, OrchestrationRun } from '../types';
import {
  useListOrchestrations,
  useCreateOrchestration,
  useUpdateOrchestration,
  useDeleteOrchestration,
  useRunOrchestration,
  useListOrchestrationRuns,
} from '../hooks/useOrchestration';
import { logger } from '../utils/logger';

const { Title, Text } = Typography;

export default function OrchestrationPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Orchestration | null>(null);
  const [viewOrch, setViewOrch] = useState<Orchestration | null>(null);
  const [form] = Form.useForm();

  const { data: orchestrations, isLoading } = useListOrchestrations();
  const createMutation = useCreateOrchestration();
  const updateMutation = useUpdateOrchestration();
  const deleteMutation = useDeleteOrchestration();
  const runMutation = useRunOrchestration();
  const { data: runs } = useListOrchestrationRuns(viewOrch?.id ?? '');

  const handleCreate = () => {
    setEditing(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: Orchestration) => {
    setEditing(record);
    form.setFieldsValue(record);
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        logger.info('OrchestrationPage', 'update_start', { id: editing.id });
        await updateMutation.mutateAsync({ id: editing.id, ...values });
      } else {
        logger.info('OrchestrationPage', 'create_start');
        await createMutation.mutateAsync(values);
      }
      setDrawerOpen(false);
    } catch (e) {
      const err = e as Record<string, unknown>;
      const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e));
      logger.error('OrchestrationPage', editing ? 'update_failed' : 'create_failed', { id: editing?.id }, msg);
    }
  };

  const handleRun = async (id: string) => {
    Modal.confirm({
      title: '确认运行',
      content: '确定要运行此编排吗？',
      onOk: async () => {
        try {
          logger.info('OrchestrationPage', 'run_start', { id });
          await runMutation.mutateAsync(id);
        } catch (e) {
          const err = e as Record<string, unknown>;
          const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e));
          logger.error('OrchestrationPage', 'run_failed', { id }, msg);
        }
      },
    });
  };

  const columns: ColumnsType<Orchestration> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '版本', dataIndex: 'version', key: 'version' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
    {
      title: '节点数',
      key: 'nodes_count',
      render: (_, record) => record.nodes?.length ?? 0,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setViewOrch(record)} />
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleRun(record.id)}>运行</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={async () => { try { logger.info('OrchestrationPage', 'delete_start', { id: record.id }); await deleteMutation.mutateAsync(record.id); } catch (e) { const err = e as Record<string, unknown>; const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e)); logger.error('OrchestrationPage', 'delete_failed', { id: record.id }, msg); } }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const nodeColumns: ColumnsType<OrchestrationNode> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
  ];

  const edgeColumns: ColumnsType<OrchestrationEdge> = [
    { title: '源节点', dataIndex: 'source_node_id', key: 'source' },
    { title: '目标节点', dataIndex: 'target_node_id', key: 'target' },
    { title: '源端口', dataIndex: 'source_port', key: 'source_port' },
    { title: '目标端口', dataIndex: 'target_port', key: 'target_port' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>编排管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建编排</Button>
      </div>

      <Table columns={columns} dataSource={orchestrations ?? []} rowKey="id" loading={isLoading} />

      {/* 详情 Drawer */}
      <Drawer title="编排详情" open={!!viewOrch} onClose={() => setViewOrch(null)} width={700}>
        {viewOrch && (
          <div>
            <Title level={5}>{viewOrch.name}</Title>
            <Text type="secondary">{viewOrch.description || '无描述'}</Text>
            <Tag style={{ marginLeft: 8 }}>{viewOrch.status}</Tag>

            <Title level={5} style={{ marginTop: 24 }}>节点</Title>
            <InnerTable columns={nodeColumns} dataSource={viewOrch.nodes} rowKey="id" size="small" pagination={false} />

            <Title level={5} style={{ marginTop: 24 }}>连线</Title>
            <InnerTable columns={edgeColumns} dataSource={viewOrch.edges} rowKey="id" size="small" pagination={false} />

            <Title level={5} style={{ marginTop: 24 }}>运行历史</Title>
            {runs && runs.length > 0 ? (
              <List
                dataSource={runs}
                renderItem={(run: OrchestrationRun) => (
                  <List.Item>
                    <Space>
                      <Tag color={run.status === 'success' ? 'green' : run.status === 'failed' ? 'red' : 'blue'}>
                        {run.status}
                      </Tag>
                      <Text type="secondary">
                        {new Date(run.started_at).toLocaleString('zh-CN')}
                      </Text>
                      {run.finished_at && (
                        <Text type="secondary">
                          → {new Date(run.finished_at).toLocaleString('zh-CN')}
                        </Text>
                      )}
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Text type="secondary">暂无运行记录</Text>
            )}
          </div>
        )}
      </Drawer>

      {/* 新建/编辑 Drawer */}
      <Drawer
        title={editing ? '编辑编排' : '新建编排'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={420}
        extra={
          <Button type="primary" onClick={handleSave} loading={createMutation.isPending || updateMutation.isPending}>
            {editing ? '更新' : '保存'}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
