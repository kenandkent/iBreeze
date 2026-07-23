import { useState } from 'react';
import { Table, Button, Modal, Form, Input, Tag, Space, Popconfirm, message } from 'antd';
import { PlusOutlined, DeleteOutlined, StopOutlined } from '@ant-design/icons';
import { useListSkills, useInstallSkill, useRemoveSkill } from '../hooks/useSkills';
import type { SkillCatalogItem } from '../types';

export default function SkillPage() {
  const { data, isLoading } = useListSkills();
  const installSkill = useInstallSkill();
  const removeSkill = useRemoveSkill();

  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const skills = data?.data ?? [];

  const handleInstall = async () => {
    const values = await form.validateFields();
    try {
      await installSkill.mutateAsync(values);
      message.success('安装成功');
      setModalOpen(false);
      form.resetFields();
    } catch {
      message.error('安装失败');
    }
  };

  const handleRemove = async (id: string) => {
    try {
      await removeSkill.mutateAsync(id);
      message.success('移除成功');
    } catch {
      message.error('移除失败');
    }
  };

  const columns = [
    { title: 'Skill Key', dataIndex: 'skill_key', key: 'skill_key' },
    { title: '版本', dataIndex: 'version', key: 'version' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (status: string) => {
        const map: Record<string, { color: string; label: string }> = {
          draft: { color: 'default', label: '草稿' },
          validated: { color: 'processing', label: '已验证' },
          published: { color: 'success', label: '已发布' },
        };
        const s = map[status];
        return s ? <Tag color={s.color}>{s.label}</Tag> : status;
      },
    },
    {
      title: '绑定 Agent', dataIndex: 'agent_bindings', key: 'agent_bindings',
      render: (bindings: string[]) => bindings?.map((b) => <Tag key={b}>{b}</Tag>) ?? '-',
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: SkillCatalogItem) => (
        <Space>
          <Popconfirm title="确认移除？需要确保绑定的 Agent 未在运行。" onConfirm={() => handleRemove(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              移除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>Skill 包管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalOpen(true); }}>
          安装 Skill
        </Button>
      </div>
      <Table dataSource={skills} columns={columns} rowKey="id" loading={isLoading} />

      <Modal
        title="安装 Skill 包"
        open={modalOpen}
        onOk={handleInstall}
        onCancel={() => setModalOpen(false)}
        confirmLoading={installSkill.isPending}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="skill_key" label="Skill Key" rules={[{ required: true, message: '请输入 Skill Key' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="version" label="版本" rules={[{ required: true, message: '请输入版本号' }]}>
            <Input placeholder="1.0.0" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
