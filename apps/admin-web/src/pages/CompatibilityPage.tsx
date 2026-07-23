import { useState } from 'react';
import { Table, Button, Modal, Form, Input, InputNumber, Select, Tag, Switch, Space, Popconfirm, Card, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useListCompatibilityRules, useCreateCompatibilityRule, useUpdateCompatibilityRule, useDeleteCompatibilityRule, useEvaluateCompatibilityRule } from '../hooks/useCompatibility';
import type { CompatibilityRule } from '../types';

const ACTION_MAP: Record<string, { color: string; label: string }> = {
  allow: { color: 'green', label: '允许' },
  deny: { color: 'red', label: '拒绝' },
  fallback: { color: 'orange', label: '回退' },
};

export default function CompatibilityPage() {
  const { data, isLoading } = useListCompatibilityRules();
  const createRule = useCreateCompatibilityRule();
  const updateRule = useUpdateCompatibilityRule();
  const deleteRule = useDeleteCompatibilityRule();
  const evaluateRule = useEvaluateCompatibilityRule();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CompatibilityRule | null>(null);
  const [testModalOpen, setTestModalOpen] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();

  const rules = data?.data ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: CompatibilityRule) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateRule.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createRule.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteRule.mutateAsync(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggleEnabled = async (record: CompatibilityRule) => {
    try {
      await updateRule.mutateAsync({ id: record.id, enabled: !record.enabled });
      message.success(record.enabled ? '已禁用' : '已启用');
    } catch {
      message.error('操作失败');
    }
  };

  const handleTest = async () => {
    const values = await testForm.validateFields();
    try {
      const result = await evaluateRule.mutateAsync(values);
      setTestResult(result.result);
    } catch {
      setTestResult('评估失败');
    }
  };

  const columns = [
    { title: 'Agent Key', dataIndex: 'agent_key', key: 'agent_key' },
    { title: '模型 Key', dataIndex: 'model_key', key: 'model_key' },
    { title: '提供商 Key', dataIndex: 'provider_key', key: 'provider_key', render: (v: string) => v ?? '-' },
    {
      title: '动作', dataIndex: 'action', key: 'action',
      render: (action: string) => {
        const a = ACTION_MAP[action];
        return a ? <Tag color={a.color}>{a.label}</Tag> : action;
      },
    },
    { title: '优先级', dataIndex: 'priority', key: 'priority' },
    {
      title: '启用', dataIndex: 'enabled', key: 'enabled',
      render: (enabled: boolean, record: CompatibilityRule) => (
        <Switch checked={enabled} onChange={() => handleToggleEnabled(record)} />
      ),
    },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: CompatibilityRule) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>兼容性规则管理</h2>
        <Space>
          <Button icon={<ExperimentOutlined />} onClick={() => { testForm.resetFields(); setTestResult(null); setTestModalOpen(true); }}>
            测试兼容性
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建规则</Button>
        </Space>
      </div>
      <Table dataSource={rules} columns={columns} rowKey="id" loading={isLoading} />

      <Modal
        title={editing ? '编辑规则' : '新建规则'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createRule.isPending || updateRule.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="agent_key" label="Agent Key" rules={[{ required: true, message: '请输入 Agent Key' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model_key" label="模型 Key" rules={[{ required: true, message: '请输入模型 Key' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="provider_key" label="提供商 Key">
            <Input />
          </Form.Item>
          <Form.Item name="platform" label="平台">
            <Input placeholder="macos / linux / windows" />
          </Form.Item>
          <Form.Item name="action" label="动作" rules={[{ required: true, message: '请选择动作' }]}>
            <Select>
              <Select.Option value="allow">允许</Select.Option>
              <Select.Option value="deny">拒绝</Select.Option>
              <Select.Option value="fallback">回退</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="fallback_model_key" label="回退模型 Key">
            <Input />
          </Form.Item>
          <Form.Item name="priority" label="优先级" rules={[{ required: true, message: '请输入优先级' }]}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="enabled" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="测试兼容性"
        open={testModalOpen}
        onOk={handleTest}
        onCancel={() => setTestModalOpen(false)}
        confirmLoading={evaluateRule.isPending}
      >
        <Form form={testForm} layout="vertical">
          <Form.Item name="agent_key" label="Agent Key" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model_key" label="模型 Key" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="provider_key" label="提供商 Key">
            <Input />
          </Form.Item>
        </Form>
        {testResult && (
          <Card size="small" style={{ marginTop: 16 }}>
            <strong>结果：</strong> {testResult}
          </Card>
        )}
      </Modal>
    </div>
  );
}
