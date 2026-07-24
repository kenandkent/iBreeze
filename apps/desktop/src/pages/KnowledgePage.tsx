import { useState } from 'react';
import {
  Table, Button, Input, Space, Tag, Drawer, Form, Select, Card, Row, Col, Statistic, Typography, Popconfirm,
} from 'antd';
import { PlusOutlined, SearchOutlined, EditOutlined, EyeOutlined, InboxOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { KnowledgeEntry } from '../types';
import {
  useListKnowledgeEntries,
  useCreateKnowledgeEntry,
  useUpdateKnowledgeEntry,
  useArchiveKnowledgeEntry,
} from '../hooks/useKnowledge';
import { logger } from '../utils/logger';

const { Title, Text } = Typography;

const typeColor: Record<string, string> = { FAQ: 'blue', DOC: 'green', URL: 'orange' };

export default function KnowledgePage() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<KnowledgeEntry | null>(null);
  const [viewEntry, setViewEntry] = useState<KnowledgeEntry | null>(null);
  const [form] = Form.useForm();

  const { data, isLoading } = useListKnowledgeEntries();
  const createMutation = useCreateKnowledgeEntry();
  const updateMutation = useUpdateKnowledgeEntry();
  const archiveMutation = useArchiveKnowledgeEntry();

  const entries = data ?? [];
  const total = entries.length;

  const handleCreate = () => {
    setEditingEntry(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: KnowledgeEntry) => {
    setEditingEntry(record);
    form.setFieldsValue(record);
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editingEntry) {
        logger.info('KnowledgePage', 'update_start', { id: editingEntry.id });
        await updateMutation.mutateAsync({ id: editingEntry.id, ...values });
      } else {
        logger.info('KnowledgePage', 'create_start');
        await createMutation.mutateAsync(values);
      }
      setDrawerOpen(false);
    } catch (e) {
      const err = e as Record<string, unknown>;
      const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e));
      logger.error('KnowledgePage', editingEntry ? 'update_failed' : 'create_failed', { id: editingEntry?.id }, msg);
    }
  };

  const columns: ColumnsType<KnowledgeEntry> = [
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (t: string) => <Tag color={typeColor[t] || 'default'}>{t}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s === 'active' ? '活跃' : '已归档'}</Tag>,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <Space wrap size={4}>
          {tags.map((t) => <Tag key={t}>{t}</Tag>)}
        </Space>
      ),
    },
    { title: '版本', dataIndex: 'version', key: 'version' },
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
          <Button size="small" icon={<EyeOutlined />} onClick={() => setViewEntry(record)} />
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          {record.status === 'active' && (
            <Popconfirm title="确认归档？" onConfirm={async () => { try { logger.info('KnowledgePage', 'archive_start', { id: record.id }); await archiveMutation.mutateAsync(record.id); } catch (e) { const err = e as Record<string, unknown>; const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e)); logger.error('KnowledgePage', 'archive_failed', { id: record.id }, msg); } }}>
              <Button size="small" icon={<InboxOutlined />}>归档</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>知识库管理</Title>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="总条目" value={total} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="FAQ" value={entries.filter((e) => e.type === 'FAQ').length} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="DOC" value={entries.filter((e) => e.type === 'DOC').length} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="URL" value={entries.filter((e) => e.type === 'URL').length} /></Card>
        </Col>
      </Row>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <Input prefix={<SearchOutlined />} placeholder="搜索" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 200 }} />
          <Select placeholder="类型" allowClear value={typeFilter} onChange={setTypeFilter} style={{ width: 120 }}>
            <Select.Option value="FAQ">FAQ</Select.Option>
            <Select.Option value="DOC">DOC</Select.Option>
            <Select.Option value="URL">URL</Select.Option>
          </Select>
          <Select placeholder="状态" allowClear value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
            <Select.Option value="active">活跃</Select.Option>
            <Select.Option value="archived">已归档</Select.Option>
          </Select>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建</Button>
      </div>

      <Table columns={columns} dataSource={entries} rowKey="id" loading={isLoading} />

      {/* 查看详情 Drawer */}
      <Drawer title="知识条目详情" open={!!viewEntry} onClose={() => setViewEntry(null)} width={600}>
        {viewEntry && (
          <div>
            <Title level={5}>{viewEntry.title}</Title>
            <Space style={{ marginBottom: 12 }}>
              <Tag color={typeColor[viewEntry.type]}>{viewEntry.type}</Tag>
              <Tag color={viewEntry.status === 'active' ? 'green' : 'default'}>
                {viewEntry.status === 'active' ? '活跃' : '已归档'}
              </Tag>
              <Text type="secondary">版本 {viewEntry.version}</Text>
            </Space>
            <Space wrap style={{ marginBottom: 12 }}>
              {viewEntry.tags.map((t) => <Tag key={t}>{t}</Tag>)}
            </Space>
            <div style={{ background: '#fafafa', padding: 16, borderRadius: 6, whiteSpace: 'pre-wrap' }}>
              {viewEntry.content}
            </div>
          </div>
        )}
      </Drawer>

      {/* 新建/编辑 Drawer */}
      <Drawer
        title={editingEntry ? '编辑知识条目' : '新建知识条目'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={480}
        extra={
          <Button type="primary" onClick={handleSave} loading={createMutation.isPending || updateMutation.isPending}>
            {editingEntry ? '更新' : '保存'}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select>
              <Select.Option value="FAQ">FAQ</Select.Option>
              <Select.Option value="DOC">DOC</Select.Option>
              <Select.Option value="URL">URL</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请输入内容' }]}>
            <Input.TextArea rows={6} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
