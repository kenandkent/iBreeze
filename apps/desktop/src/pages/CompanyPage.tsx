import { useState } from 'react';
import {
  Table, Button, Input, Space, Tag, Drawer, Form, Popconfirm, Select, Typography,
} from 'antd';
import { PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Company } from '../types';
import { useListCompanies, useCreateCompany, useUpdateCompany, useDeleteCompany } from '../hooks/useCompany';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function CompanyPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCompany, setEditingCompany] = useState<Company | null>(null);
  const [form] = Form.useForm();

  const { data, isLoading } = useListCompanies({ search, status: statusFilter === 'all' ? undefined : statusFilter });
  const createMutation = useCreateCompany();
  const updateMutation = useUpdateCompany();
  const deleteMutation = useDeleteCompany();

  const handleCreate = () => {
    setEditingCompany(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: Company) => {
    setEditingCompany(record);
    form.setFieldsValue(record);
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      if (editingCompany) {
        logger.info('CompanyPage', 'update_start', { id: editingCompany.id });
        await updateMutation.mutateAsync({ id: editingCompany.id, ...values });
      } else {
        logger.info('CompanyPage', 'create_start');
        await createMutation.mutateAsync(values);
      }
      setDrawerOpen(false);
    } catch (e) {
      const err = e as Record<string, unknown>;
      const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e));
      logger.error('CompanyPage', editingCompany ? 'update_failed' : 'create_failed', { id: editingCompany?.id }, msg);
    }
  };

  const columns: ColumnsType<Company> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '行业', dataIndex: 'industry', key: 'industry' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
      ),
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
          <Button size="small" icon={<EyeOutlined />} onClick={() => { setEditingCompany(record); setDrawerOpen(true); }} />
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={async () => { try { logger.info('CompanyPage', 'delete_start', { id: record.id }); await deleteMutation.mutateAsync(record.id); } catch (e) { const err = e as Record<string, unknown>; const msg = (err?.error as string) || (e instanceof Error ? e.message : String(e)); logger.error('CompanyPage', 'delete_failed', { id: record.id }, msg); } }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>企业管理</Title>
        <Space>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索企业"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 200 }}
          />
          <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
            <Select.Option value="all">全部状态</Select.Option>
            <Select.Option value="active">活跃</Select.Option>
            <Select.Option value="inactive">归档</Select.Option>
          </Select>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建企业</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data ?? []} rowKey="id" loading={isLoading} />

      <Drawer
        title={editingCompany ? '编辑企业' : '新建企业'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={480}
        extra={
          editingCompany ? undefined : (
            <Button type="primary" onClick={handleSave} loading={createMutation.isPending}>保存</Button>
          )
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="企业名称" rules={[{ required: true, message: '请输入企业名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="industry" label="行业">
            <Input />
          </Form.Item>
        </Form>
        {editingCompany && (
          <Space style={{ marginTop: 16 }}>
            <Button type="primary" onClick={handleSave} loading={updateMutation.isPending}>更新</Button>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
