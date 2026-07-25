import { useState, useEffect } from 'react';
import {
  Table, Button, Drawer, Form, Input, Space, Tag, Typography, Popconfirm,
} from 'antd';
import { PlusOutlined, EyeOutlined, InboxOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { invoke } from '@tauri-apps/api/core';
import { logger } from '../utils/logger';

const { Title, Text } = Typography;

interface Skill {
  id: string;
  name: string;
  version: string;
  description: string;
  status: 'active' | 'archived';
  created_at: string;
}

export default function SkillsPage() {
  useEffect(() => { logger.logPageInit('SkillsPage'); }, []);

  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [viewSkill, setViewSkill] = useState<Skill | null>(null);
  const [form] = Form.useForm();

  const loadSkills = async () => {
    setLoading(true);
    try {
      const result = await invoke<{ skills: Skill[] }>('rpc_request', { method: 'skill.list', params: {} });
      setSkills(result?.skills || []);
      logger.logPageLoad('SkillsPage', { count: result?.skills?.length });
    } catch (e) {
      logger.logPageError('SkillsPage', e as Error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSkills(); }, []);

  const handleCreate = async () => {
    const values = await form.validateFields();
    try {
      logger.logAction('SkillsPage', 'create_skill');
      await invoke('rpc_request', { method: 'skill.create', params: values });
      setDrawerOpen(false);
      form.resetFields();
      loadSkills();
    } catch (e) {
      logger.logPageError('SkillsPage', e as Error);
    }
  };

  const handleArchive = async (id: string) => {
    try {
      logger.logAction('SkillsPage', 'archive_skill', { id });
      await invoke('rpc_request', { method: 'skill.archive', params: { id } });
      loadSkills();
    } catch (e) {
      logger.logPageError('SkillsPage', e as Error);
    }
  };

  const columns: ColumnsType<Skill> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '版本', dataIndex: 'version', key: 'version' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s === 'active' ? '活跃' : '已归档'}</Tag>,
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
          <Button size="small" icon={<EyeOutlined />} onClick={() => setViewSkill(record)} />
          {record.status === 'active' && (
            <Popconfirm title="确认归档？" onConfirm={() => handleArchive(record.id)}>
              <Button size="small" icon={<InboxOutlined />}>归档</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>技能管理</Title>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>新建技能</Button>
      </div>

      <Table columns={columns} dataSource={skills} rowKey="id" loading={loading} />

      <Drawer title="技能详情" open={!!viewSkill} onClose={() => setViewSkill(null)} width={600}>
        {viewSkill && (
          <div>
            <Title level={5}>{viewSkill.name}</Title>
            <Space style={{ marginBottom: 12 }}>
              <Tag color={viewSkill.status === 'active' ? 'green' : 'default'}>
                {viewSkill.status === 'active' ? '活跃' : '已归档'}
              </Tag>
              <Text type="secondary">版本 {viewSkill.version}</Text>
            </Space>
            <div style={{ background: '#fafafa', padding: 16, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
              {viewSkill.description}
            </div>
          </div>
        )}
      </Drawer>

      <Drawer
        title="新建技能"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={480}
        extra={<Button type="primary" onClick={handleCreate}>保存</Button>}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="技能名称" rules={[{ required: true, message: '请输入技能名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="version" label="版本" rules={[{ required: true, message: '请输入版本号' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
