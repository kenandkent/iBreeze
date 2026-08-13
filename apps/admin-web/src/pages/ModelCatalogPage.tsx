import { useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Tag, Space, Popconfirm, Checkbox, Select, message } from 'antd';
import { logger } from '../utils/logger';
import { formatNumber } from '../utils/formatters';
import { PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useListModels, useCreateModel, useUpdateModel, useDeleteModel, useValidateModel } from '../hooks/useModelCatalog';
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

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelCatalogItem | null>(null);
  const [form] = Form.useForm();

  const models = data?.items ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      routing_tier: 1,
      quality_prior: 0.5,
      tool_reliability_prior: 0.5,
      latency_prior_ms: 3000,
      architecture_class: 'unknown',
      supports_reasoning: false,
      reasoning_levels: [],
      input_price_microusd_per_million: 0,
      output_price_microusd_per_million: 0,
      routing_enabled: false,
    });
    setModalOpen(true);
  };

  const openEdit = (record: ModelCatalogItem) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const action = editing ? 'update' : 'create';
    logger.info('ModelCatalogPage', `${action}_start`, { id: editing?.id, model_key: values.model_key });
    try {
      if (editing) {
        await updateModel.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createModel.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ModelCatalogPage', `${action}_failed`, { id: editing?.id, model_key: values.model_key }, msg);
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    logger.info('ModelCatalogPage', 'delete_start', { id });
    try {
      await deleteModel.mutateAsync(id);
      message.success('删除成功');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ModelCatalogPage', 'delete_failed', { id }, msg);
      message.error('删除失败');
    }
  };

  const handleValidate = async (id: string) => {
    logger.info('ModelCatalogPage', 'validate_start', { id });
    try {
      await validateModel.mutateAsync(id);
      message.success('验证成功');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logger.error('ModelCatalogPage', 'validate_failed', { id }, msg);
      message.error('验证失败');
    }
  };


  const columns = [
    { title: '提供商', dataIndex: 'provider_key', key: 'provider_key' },
    { title: '模型 Key', dataIndex: 'model_key', key: 'model_key' },
    { title: '显示名称', dataIndex: 'display_name', key: 'display_name' },
    { title: '上下文窗口', dataIndex: 'context_window', key: 'context_window', render: (v: number) => formatNumber(v) ?? '-' },
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
      title: '路由元数据', key: 'routing',
      render: (_: unknown, record: ModelCatalogItem) => (
        <Space size="small">
          <Tag>Tier {record.routing_tier}</Tag>
          <Tag color={record.routing_enabled ? 'green' : 'default'}>
            {record.routing_enabled ? '智能路由' : '固定路由'}
          </Tag>
          <span>{record.model_vendor}/{record.model_family}</span>
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
                <Tag color="processing">已验证（通过发布流程发布）</Tag>
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
          <Form.Item name="model_family" label="模型家族" rules={[{ required: true, message: '请输入模型家族' }]}>
            <Input placeholder="例如 gpt、claude、qwen" />
          </Form.Item>
          <Form.Item name="model_vendor" label="模型厂商" rules={[{ required: true, message: '请输入模型厂商' }]}>
            <Input placeholder="例如 openai、anthropic" />
          </Form.Item>
          <Form.Item name="routing_tier" label="路由等级" rules={[{ required: true, message: '请选择路由等级' }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={3} precision={0} />
          </Form.Item>
          <Form.Item name="quality_prior" label="质量先验" rules={[{ required: true, message: '请输入质量先验' }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.0001} precision={4} />
          </Form.Item>
          <Form.Item name="tool_reliability_prior" label="工具可靠性先验" rules={[{ required: true, message: '请输入工具可靠性先验' }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.0001} precision={4} />
          </Form.Item>
          <Form.Item name="latency_prior_ms" label="延迟先验（毫秒）" rules={[{ required: true, message: '请输入延迟先验' }]}>
            <InputNumber style={{ width: '100%' }} min={1} precision={0} />
          </Form.Item>
          <Form.Item name="architecture_class" label="架构类型" rules={[{ required: true, message: '请选择架构类型' }]}>
            <Select options={[
              { value: 'dense', label: 'Dense' },
              { value: 'moe', label: 'MoE' },
              { value: 'hybrid', label: 'Hybrid' },
              { value: 'unknown', label: 'Unknown' },
            ]} />
          </Form.Item>
          <Form.Item name="supports_reasoning" valuePropName="checked">
            <Checkbox>支持推理</Checkbox>
          </Form.Item>
          <Form.Item noStyle dependencies={['supports_reasoning']}>
            {({ getFieldValue }) => (
              <Form.Item name="reasoning_levels" label="推理等级">
                <Select
                  mode="multiple"
                  disabled={!getFieldValue('supports_reasoning')}
                  options={[
                    { value: 'low', label: 'Low' },
                    { value: 'medium', label: 'Medium' },
                    { value: 'high', label: 'High' },
                  ]}
                />
              </Form.Item>
            )}
          </Form.Item>
          <Form.Item name="input_price_microusd_per_million" label="输入价格（微美元/百万 token）" rules={[{ required: true, message: '请输入输入价格' }]}>
            <InputNumber style={{ width: '100%' }} min={0} precision={0} />
          </Form.Item>
          <Form.Item name="output_price_microusd_per_million" label="输出价格（微美元/百万 token）" rules={[{ required: true, message: '请输入输出价格' }]}>
            <InputNumber style={{ width: '100%' }} min={0} precision={0} />
          </Form.Item>
          <Form.Item name="routing_enabled" valuePropName="checked">
            <Checkbox>启用智能路由候选</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
