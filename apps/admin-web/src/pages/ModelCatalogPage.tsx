import { useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Tag, Space, Popconfirm, Checkbox, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useListModels, useCreateModel, useUpdateModel, useDeleteModel, useValidateModel, usePublishModel } from '../hooks/useModelCatalog';
import type { ModelCatalogItem } from '../types';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  validated: { color: 'processing', label: '已验证' },
  published: { color: 'success', label: '已发布' },
};

export default function ModelCatalogPage() {
  const { data, isLoading } = useListModels();
  const createModel = useCreateModel();
  const updateModel = useUpdateModel();
  const deleteModel = useDeleteModel();
  const validateModel = useValidateModel();
  const publishModel = usePublishModel();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelCatalogItem | null>(null);
  const [form] = Form.useForm();

  const models = data?.data ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: ModelCatalogItem) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateModel.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createModel.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteModel.mutateAsync(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleValidate = async (id: string) => {
    try {
      await validateModel.mutateAsync(id);
      message.success('验证成功');
    } catch {
      message.error('验证失败');
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await publishModel.mutateAsync(id);
      message.success('发布成功');
    } catch {
      message.error('发布失败');
    }
  };

  const columns = [
    { title: '提供商', dataIndex: 'provider_key', key: 'provider_key' },
    { title: '模型 Key', dataIndex: 'model_key', key: 'model_key' },
    { title: '显示名称', dataIndex: 'display_name', key: 'display_name' },
    { title: '上下文窗口', dataIndex: 'context_window', key: 'context_window', render: (v: number) => v?.toLocaleString() ?? '-' },
    {
      title: '能力', key: 'capabilities',
      render: (_: unknown, record: ModelCatalogItem) => (
        <Space>
          {record.supports_tools && <Tag color="blue">Tools</Tag>}
          {record.supports_streaming && <Tag color="cyan">Streaming</Tag>}
          {record.supports_vision && <Tag color="purple">Vision</Tag>}
        </Space>
      ),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => {
        const s = STATUS_MAP[status];
        return s ? <Tag color={s.color}>{s.label}</Tag> : status;
      },
    },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: ModelCatalogItem) => (
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
        <h2>模型管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建模型</Button>
      </div>
      <Table dataSource={models} columns={columns} rowKey="id" loading={isLoading} />
      <Modal
        title={editing ? '编辑模型' : '新建模型'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createModel.isPending || updateModel.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="provider_key" label="提供商 Key" rules={[{ required: true, message: '请输入提供商 Key' }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="model_key" label="模型 Key" rules={[{ required: true, message: '请输入模型 Key' }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入显示名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="context_window" label="上下文窗口">
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="supports_tools" valuePropName="checked">
            <Checkbox>支持工具调用</Checkbox>
          </Form.Item>
          <Form.Item name="supports_streaming" valuePropName="checked">
            <Checkbox>支持流式输出</Checkbox>
          </Form.Item>
          <Form.Item name="supports_vision" valuePropName="checked">
            <Checkbox>支持视觉能力</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
