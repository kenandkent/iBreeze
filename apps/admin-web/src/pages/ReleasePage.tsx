import { useState } from 'react';
import { Table, Button, Modal, Drawer, Form, Input, Space, Typography, message } from 'antd';
import { PlusOutlined, EyeOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { logger } from '../utils/logger';
import { useListReleases, useCreateRelease, useEmergencyDisable } from '../hooks/useReleases';
import type { Release } from '../types';

const { Text } = Typography;

export default function ReleasePage() {
  const { data, isLoading } = useListReleases();
  const createRelease = useCreateRelease();
  const emergencyDisable = useEmergencyDisable();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [drawerRelease, setDrawerRelease] = useState<Release | null>(null);
  const [emergencyModal, setEmergencyModal] = useState(false);
  const [form] = Form.useForm();
  const [emergencyForm] = Form.useForm();

  const releases = data?.data ?? [];

  const handleCreate = async () => {
    const values = await form.validateFields();
    try {
      await createRelease.mutateAsync(values);
      message.success('发布创建成功');
      setCreateModalOpen(false);
      form.resetFields();
    } catch (error) {
      logger.error('ReleasePage', 'create_release_failed', undefined, error);
      message.error('发布创建失败');
    }
  };

  const handleEmergencyDisable = async () => {
    const values = await emergencyForm.validateFields();
    try {
      await emergencyDisable.mutateAsync(values);
      message.success('紧急禁用已执行');
      setEmergencyModal(false);
      emergencyForm.resetFields();
    } catch (error) {
      logger.error('ReleasePage', 'emergency_disable_failed', undefined, error);
      message.error('紧急禁用失败');
    }
  };

  const columns = [
    { title: '版本', dataIndex: 'version', key: 'version' },
    { title: '发布序号', dataIndex: 'release_sequence', key: 'release_sequence' },
    {
      title: '签名', dataIndex: 'signature', key: 'signature',
      render: (sig: string) => sig ? <Text copyable ellipsis style={{ maxWidth: 200 }}>{sig}</Text> : '-',
    },
    { title: '签名密钥 ID', dataIndex: 'signing_key_id', key: 'signing_key_id' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: Release) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setDrawerRelease(record)}>
            查看 Manifest
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>发布管理</h2>
        <Space>
          <Button danger icon={<ExclamationCircleOutlined />} onClick={() => { emergencyForm.resetFields(); setEmergencyModal(true); }}>
            紧急禁用
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateModalOpen(true); }}>
            新建发布
          </Button>
        </Space>
      </div>
      <Table dataSource={releases} columns={columns} rowKey="id" loading={isLoading} />

      <Modal
        title="新建发布"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => setCreateModalOpen(false)}
        confirmLoading={createRelease.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="version" label="版本号" rules={[{ required: true, message: '请输入版本号' }]}>
            <Input placeholder="1.0.0" />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="紧急禁用"
        open={emergencyModal}
        onOk={handleEmergencyDisable}
        onCancel={() => setEmergencyModal(false)}
        okButtonProps={{ danger: true }}
        confirmLoading={emergencyDisable.isPending}
      >
        <Form form={emergencyForm} layout="vertical">
          <Form.Item name="resource_type" label="资源类型" rules={[{ required: true, message: '请输入资源类型' }]}>
            <Input placeholder="agents / models / providers / skills" />
          </Form.Item>
          <Form.Item name="resource_id" label="资源 ID" rules={[{ required: true, message: '请输入资源 ID' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="reason" label="原因" rules={[{ required: true, message: '请输入禁用原因' }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="emergency_code" label="紧急代码" rules={[{ required: true, message: '请输入紧急代码确认' }]}>
            <Input placeholder="输入 EMERGENCY 确认" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="Manifest 详情"
        open={!!drawerRelease}
        onClose={() => setDrawerRelease(null)}
        width={600}
      >
        {drawerRelease && (
          <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, overflow: 'auto', maxHeight: '80vh' }}>
            {JSON.stringify(drawerRelease.manifest, null, 2)}
          </pre>
        )}
      </Drawer>
    </div>
  );
}
