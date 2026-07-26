import { useState, useEffect } from 'react';
import { Card, Typography, Table, Button, Space, Modal, Form, Input, Select, Popconfirm, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SwapOutlined } from '@ant-design/icons';
import { useListEmployees, useCreateEmployee } from '../hooks/useEmployee';
import { useListDepartments } from '../hooks/useDepartment';
import { formatTime } from '../utils/formatters';
import type { Employee } from '../types';
import { logger } from '../utils/logger';

const { Title } = Typography;

export default function EmployeePage() {
  useEffect(() => { logger.logPageInit('EmployeePage'); }, []);

  const companyId = 'default';
  const { data: empData, isLoading } = useListEmployees(companyId);
  const employees = empData?.items ?? [];
  const { data: deptData } = useListDepartments(companyId);
  const departments = deptData?.items ?? [];
  const createEmp = useCreateEmployee();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const columns = [
    { title: '姓名', dataIndex: 'display_name', key: 'display_name' },
    { title: '角色', dataIndex: 'role', key: 'role' },
    { title: '部门', dataIndex: 'department_id', key: 'department_id', render: (id: string) => departments.find((d) => d.id === id)?.name || id },
    { title: '状态', dataIndex: 'status', key: 'status' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', render: (v: string) => formatTime(v) },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, _record: Employee) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => { logger.logAction('EmployeePage', 'edit_employee'); setModalOpen(true); }}>编辑</Button>
          <Button size="small" icon={<SwapOutlined />} onClick={() => { logger.logAction('EmployeePage', 'transfer_employee'); }}>调岗</Button>
          <Popconfirm title="确认删除？" onConfirm={() => { logger.logAction('EmployeePage', 'delete_employee'); }}><Button size="small" danger icon={<DeleteOutlined />}>删除</Button></Popconfirm>
        </Space>
      ),
    },
  ];

  const handleSubmit = async () => {
    logger.logAction('EmployeePage', 'create_employee');
    const values = await form.validateFields();
    await createEmp.mutateAsync({
      company_id: companyId,
      department_id: values.department_id,
      display_name: values.display_name,
      base_profile_version_id: '',
      workflow_role: values.role === 'general_manager' ? 'general_manager' : values.role === 'department_head' ? 'department_leader' : 'member',
    });
    message.success('创建成功');
    setModalOpen(false);
    form.resetFields();
  };

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>员工管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加员工</Button>
      </Space>
      <Table columns={columns} dataSource={employees} rowKey="id" loading={isLoading} />
      <Modal title="添加员工" open={modalOpen} onOk={handleSubmit} onCancel={() => { setModalOpen(false); form.resetFields(); }}>
        <Form form={form} layout="vertical">
          <Form.Item name="display_name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="department_id" label="部门" rules={[{ required: true }]}>
            <Select options={departments.map((d) => ({ value: d.id, label: d.name }))} />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={[{ value: 'employee', label: '员工' }, { value: 'department_head', label: '部门负责人' }, { value: 'general_manager', label: '总经理' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
