import { useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, Tag, Space, Popconfirm, Tooltip, message } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, LockOutlined, KeyOutlined, StopOutlined } from '@ant-design/icons';
import { useListAdminUsers, useCreateAdminUser, useUpdateAdminUser, useDeleteAdminUser, useResetPassword, useRevokeSessions } from '../hooks/useAdminUsers';
import type { AdminUser } from '../types';

export default function AdminUserPage() {
  const { data, isLoading } = useListAdminUsers();
  const createUser = useCreateAdminUser();
  const updateUser = useUpdateAdminUser();
  const deleteUser = useDeleteAdminUser();
  const resetPassword = useResetPassword();
  const revokeSessions = useRevokeSessions();

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [resetPwdModal, setResetPwdModal] = useState<AdminUser | null>(null);
  const [form] = Form.useForm();
  const [resetPwdForm] = Form.useForm();

  const users = data?.data ?? [];

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: AdminUser) => {
    setEditing(record);
    form.setFieldsValue({ email: record.email, user_type: record.user_type, role: record.role });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await updateUser.mutateAsync({ id: editing.id, ...values });
        message.success('更新成功');
      } else {
        await createUser.mutateAsync(values);
        message.success('创建成功');
      }
      setModalOpen(false);
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteUser.mutateAsync(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleResetPassword = async () => {
    const values = await resetPwdForm.validateFields();
    if (!resetPwdModal) return;
    try {
      await resetPassword.mutateAsync({ id: resetPwdModal.id, new_password: values.new_password });
      message.success('密码重置成功');
      setResetPwdModal(null);
      resetPwdForm.resetFields();
    } catch {
      message.error('密码重置失败');
    }
  };

  const handleRevokeSessions = async (id: string) => {
    try {
      await revokeSessions.mutateAsync(id);
      message.success('会话已撤销');
    } catch {
      message.error('撤销失败');
    }
  };

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    {
      title: '类型', dataIndex: 'user_type', key: 'user_type',
      render: (type: string) => <Tag color={type === 'admin' ? 'blue' : 'green'}>{type === 'admin' ? '管理员' : '应用用户'}</Tag>,
    },
    { title: '角色', dataIndex: 'role', key: 'role' },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (active: boolean) => <Tag color={active ? 'success' : 'error'}>{active ? '活跃' : '禁用'}</Tag>,
    },
    {
      title: '受保护', dataIndex: 'protected', key: 'protected',
      render: (p: boolean) => p ? <Tooltip title="受保护管理员"><LockOutlined style={{ color: '#faad14' }} /></Tooltip> : null,
    },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作', key: 'actions',
      render: (_: unknown, record: AdminUser) => (
        <Space>
          {!record.protected && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
              编辑
            </Button>
          )}
          <Button type="link" size="small" icon={<KeyOutlined />} onClick={() => { setResetPwdModal(record); resetPwdForm.resetFields(); }}>
            重置密码
          </Button>
          <Button type="link" size="small" icon={<StopOutlined />} onClick={() => handleRevokeSessions(record.id)}>
            撤销会话
          </Button>
          {!record.protected && (
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <h2>用户管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建用户</Button>
      </div>
      <Table dataSource={users} columns={columns} rowKey="id" loading={isLoading} />

      <Modal
        title={editing ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={createUser.isPending || updateUser.isPending}
      >
        <Form form={form} layout="vertical">
          {!editing && (
            <>
              <Form.Item name="email" label="邮箱" rules={[{ required: true, message: '请输入邮箱' }]}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          <Form.Item name="user_type" label="用户类型" rules={[{ required: !editing, message: '请选择用户类型' }]}>
            <Select disabled={!!editing} placeholder="选择用户类型">
              <Select.Option value="admin">管理员</Select.Option>
              <Select.Option value="app_user">应用用户</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Input disabled={editing?.user_type === 'app_user'} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="重置密码"
        open={!!resetPwdModal}
        onOk={handleResetPassword}
        onCancel={() => { setResetPwdModal(null); resetPwdForm.resetFields(); }}
        confirmLoading={resetPassword.isPending}
      >
        <Form form={resetPwdForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
