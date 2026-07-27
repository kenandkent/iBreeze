import { useState } from 'react';
import { Table, Button, Modal, Drawer, Form, Input, Space, Tag, Typography, message } from 'antd';
import { PlusOutlined, EyeOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons';
import { logger } from '../utils/logger';
import { formatTime } from '../utils/formatters';
import { useListReleases, useCreateRelease, usePublishRelease, useReconcileRelease } from '../hooks/useReleases';
import type { Release } from '../types';

const { Text } = Typography;

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  publishing: { color: 'default', label: '草稿' },
  reconciled: { color: 'processing', label: '已验证' },
  published: { color: 'success', label: '已发布' },
};

export default function ReleasePage() {
  const { data, isLoading } = useListReleases();
  const createRelease = useCreateRelease();
  const publishRelease = usePublishRelease();
  const reconcileRelease = useReconcileRelease();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [drawerRelease, setDrawerRelease] = useState<Release | null>(null);
  const [form] = Form.useForm();

  const releases = data?.items ?? [];

  const handleCreate = async () => {
    const values = await form.validateFields();
    try {
      await createRelease.mutateAsync(values);
      message.success('发布草稿创建成功');
      setCreateModalOpen(false);
      form.resetFields();
    } catch (error) {
      logger.error('ReleasePage', 'create_release_failed', undefined, error);
      message.error('创建失败');
    }
  };

  const handleReconcile = async (id: string) => {
    try {
      await reconcileRelease.mutateAsync(id);
      message.success('验证通过，当前为已验证状态');
    } catch (error) {
      logger.error('ReleasePage', 'reconcile_failed', { id }, error);
      message.error('验证失败');
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await publishRelease.mutateAsync(id);
      message.success('发布成功');
    } catch (error) {
      logger.error('ReleasePage', 'publish_failed', { id }, error);
      message.error('发布失败');
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
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => {
        const s = STATUS_MAP[status];
        return s ? <Tag color={s.color}>{s.label}</Tag> : status;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => formatTime(v) },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: Release) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => setDrawerRelease(record)}>
            查看 Manifest
          </Button>
          {record.status === 'publishing' && (
            <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handleReconcile(record.id)}>
              验证
            </Button>
          )}
          {record.status === 'reconciled' && (
            <Button type="link" size="small" icon={<SendOutlined />} onClick={() => handlePublish(record.id)}>
              发布
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>发布管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateModalOpen(true); }}>
          新建发布
        </Button>
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
