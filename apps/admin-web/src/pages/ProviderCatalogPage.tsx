import { useState } from 'react';
import { Table, Button, Modal, Form, Input, Tag, Space, Popconfirm, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useListProviders, useCreateProvider, useUpdateProvider, useDeleteProvider } from '../hooks/useProviderCatalog';
import type { ProviderCatalogItem } from '../types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  validated: { color: 'processing', label: '已验证' },
  published: { color: 'success', label: '已发布' },
};

export default function ProviderCatalogPage() {
  const { data, isLoading } = useListProviders();
  const createProvider = useCreateProvider();
  const updateProvider = useUpdateProvider();
  const deleteProvider = useDeleteProvider();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProviderCatalogItem | null>(null);
  const [form] = Form.useForm();

  const providers = data?.data ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: ProviderCatalogItem) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateProvider.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createProvider.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProvider.mutateAsync(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: '显示名称', dataIndex: 'display_name', key: 'display_name' },
    { title: 'Base URL', dataIndex: 'base_url', key: 'base_url' },
    { title: 'API 协议', dataIndex: 'api_protocol', key: 'api_protocol' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => {
        const s = STATUS_MAP[status];
        return s ? <Tag color={s.color}>{s.label}</Tag> : status;
      },
    },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: ProviderCatalogItem) => (
        <Space>
          {record.status !== 'published' && (
            <>
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
                编辑
              </Button>
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
        <h2>提供商管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建提供商</Button>
      </div>
      <Table dataSource={providers} columns={columns} rowKey="id" loading={isLoading} />
      <Modal
        title={editing ? '编辑提供商' : '新建提供商'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createProvider.isPending || updateProvider.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.example.com" />
          </Form.Item>
          <Form.Item name="api_protocol" label="API 协议" rules={[{ required: true, message: '请输入 API 协议' }]}>
            <Input placeholder="openai / anthropic / custom" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
