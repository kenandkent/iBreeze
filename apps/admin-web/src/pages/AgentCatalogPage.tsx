import { useState } from 'react';
import { Table, Button, Modal, Form, Input, Tag, Space, Popconfirm, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useListAgents, useCreateAgent, useUpdateAgent, useDeleteAgent, useValidateAgent, usePublishAgent } from '../hooks/useAgentCatalog';
import type { AgentCatalogItem } from '../types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  validated: { color: 'processing', label: '已验证' },
  published: { color: 'success', label: '已发布' },
};

export default function AgentCatalogPage() {
  const { data, isLoading } = useListAgents();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const validateAgent = useValidateAgent();
  const publishAgent = usePublishAgent();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AgentCatalogItem | null>(null);
  const [form] = Form.useForm();

  const agents = data?.data ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: AgentCatalogItem) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateAgent.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createAgent.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteAgent.mutateAsync(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleValidate = async (id: string) => {
    try {
      await validateAgent.mutateAsync(id);
      message.success('验证成功');
    } catch {
      message.error('验证失败');
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await publishAgent.mutateAsync(id);
      message.success('发布成功');
    } catch {
      message.error('发布失败');
    }
  };

  const columns = [
    { title: 'Key', dataIndex: 'key', key: 'key' },
    { title: '显示名称', dataIndex: 'display_name', key: 'display_name' },
    { title: '版本', dataIndex: 'catalog_revision', key: 'catalog_revision' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => {
        const s = STATUS_MAP[status];
        return s ? <Tag color={s.color}>{s.label}</Tag> : status;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: AgentCatalogItem) => (
        <Space>
          {record.status !== 'published' && (
            <>
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
                编辑
              </Button>
              {record.status === 'draft' && (
                <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleValidate(record.id)}>
                  验证
                </Button>
              )}
              {record.status === 'validated' && (
                <Button type="link" size="small" icon={<SendOutlined />} onClick={() => handlePublish(record.id)}>
                  发布
                </Button>
              )}
              <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          )}
          {record.status === 'published' && <Tag color="success">已发布</Tag>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>Agent 管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建 Agent</Button>
      </div>
      <Table dataSource={agents} columns={columns} rowKey="id" loading={isLoading} />
      <Modal
        title={editing ? '编辑 Agent' : '新建 Agent'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createAgent.isPending || updateAgent.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="key" label="Key" rules={[{ required: !editing, message: '请输入 Key' }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
