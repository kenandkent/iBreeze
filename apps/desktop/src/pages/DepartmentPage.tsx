import { useState, useEffect } from 'react';
import { Card, Typography, Table, Button, Space, Modal, Form, Input, Popconfirm, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useListDepartments, useCreateDepartment } from '../hooks/useDepartment';
import { formatTime } from '../utils/formatters';
import type { Department } from '../types';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function DepartmentPage() {
  useEffect(() => { logger.logPageInit('DepartmentPage'); }, []);

  const companyId = 'default';
  const { data: deptData, isLoading } = useListDepartments(companyId);
  const departments = deptData?.items ?? [];
  const createDept = useCreateDepartment();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();

  const columns = [
    { title: '部门名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => formatTime(v) },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: Department) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { logger.logAction('DepartmentPage', 'edit_department'); setEditingId(record.id); setModalOpen(true); }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => { logger.logAction('DepartmentPage', 'delete_department'); }}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  const handleSubmit = async () => {
    logger.logAction('DepartmentPage', editingId ? 'edit_department' : 'create_department');
    const values = await form.validateFields();
    await createDept.mutateAsync({
      company_id: companyId,
      name: values.name,
      function_description: values.description || values.name,
      leader_name: '部门负责人',
      base_profile_version_id: '',
    });
    message.success(editingId ? '更新成功' : '创建成功');
    setModalOpen(false);
    form.resetFields();
    setEditingId(null);
  };

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>部门管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建部门</Button>
      </Space>
      <Table columns={columns} dataSource={departments} rowKey="id" loading={isLoading} />
      <Modal title={editingId ? '编辑部门' : '新建部门'} open={modalOpen} onOk={handleSubmit} onCancel={() => { setModalOpen(false); form.resetFields(); }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
