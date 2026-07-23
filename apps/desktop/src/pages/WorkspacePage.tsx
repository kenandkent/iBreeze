import { useState } from 'react';
import {
  Table, Button, Space, Tag, Drawer, Form, Input, Typography, Popconfirm, List,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, UserDeleteOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Workspace, WorkspaceMember } from '../types';
import {
  useListWorkspaces,
  useCreateWorkspace,
  useUpdateWorkspace,
  useDeleteWorkspace,
  useAddWorkspaceMember,
  useRemoveWorkspaceMember,
} from '../hooks/useWorkspace';

const { Title, Text } = Typography;

export default function WorkspacePage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingWs, setEditingWs] = useState<Workspace | null>(null);
  const [viewWs, setViewWs] = useState<Workspace | null>(null);
  const [memberDrawerOpen, setMemberDrawerOpen] = useState(false);
  const [form] = Form.useForm();
  const [memberForm] = Form.useForm();

  const { data: workspaces, isLoading } = useListWorkspaces();
  const createMutation = useCreateWorkspace();
  const updateMutation = useUpdateWorkspace();
  const deleteMutation = useDeleteWorkspace();
  const addMemberMutation = useAddWorkspaceMember();
  const removeMemberMutation = useRemoveWorkspaceMember();

  const handleCreate = () => {
    setEditingWs(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: Workspace) => {
    setEditingWs(record);
    form.setFieldsValue(record);
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    if (editingWs) {
      await updateMutation.mutateAsync({ id: editingWs.id, ...values });
    } else {
      await createMutation.mutateAsync(values);
    }
    setDrawerOpen(false);
  };

  const handleAddMember = async () => {
    const values = await memberForm.validateFields();
    if (viewWs) {
      await addMemberMutation.mutateAsync({ workspace_id: viewWs.id, ...values });
      memberForm.resetFields();
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (viewWs) {
      await removeMemberMutation.mutateAsync({ workspace_id: viewWs.id, member_id: memberId });
    }
  };

  const columns: ColumnsType<Workspace> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '成员数',
      key: 'members_count',
      render: (_, record) => record.members?.length ?? 0,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => setViewWs(record)} />
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => deleteMutation.mutateAsync(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>工作区管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建工作区</Button>
      </div>

      <Table columns={columns} dataSource={workspaces ?? []} rowKey="id" loading={isLoading} />

      {/* 详情 Drawer */}
      <Drawer title="工作区详情" open={!!viewWs} onClose={() => setViewWs(null)} width={520}>
        {viewWs && (
          <div>
            <Title level={5}>{viewWs.name}</Title>
            <Text type="secondary">{viewWs.description || '无描述'}</Text>

            <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Title level={5} style={{ margin: 0 }}>成员列表</Title>
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={() => setMemberDrawerOpen(true)}
              >
                添加成员
              </Button>
            </div>
            <List
              style={{ marginTop: 12 }}
              dataSource={viewWs.members}
              renderItem={(member: WorkspaceMember) => (
                <List.Item
                  actions={
                    member.role !== 'owner'
                      ? [
                          <Popconfirm
                            key="remove"
                            title="确认移除？"
                            onConfirm={() => handleRemoveMember(member.id)}
                          >
                            <Button size="small" danger icon={<UserDeleteOutlined />} />
                          </Popconfirm>,
                        ]
                      : []
                  }
                >
                  <List.Item.Meta
                    title={member.user_id}
                    description={<Tag>{member.role}</Tag>}
                  />
                </List.Item>
              )}
            />
          </div>
        )}
      </Drawer>

      {/* 添加成员 Drawer */}
      <Drawer title="添加成员" open={memberDrawerOpen} onClose={() => setMemberDrawerOpen(false)} width={360}>
        <Form form={memberForm} layout="vertical">
          <Form.Item name="user_id" label="用户 ID" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="member">
            <Input />
          </Form.Item>
        </Form>
        <Button type="primary" onClick={handleAddMember} loading={addMemberMutation.isPending}>添加</Button>
      </Drawer>

      {/* 新建/编辑 Drawer */}
      <Drawer
        title={editingWs ? '编辑工作区' : '新建工作区'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={420}
        extra={
          <Button type="primary" onClick={handleSave} loading={createMutation.isPending || updateMutation.isPending}>
            {editingWs ? '更新' : '保存'}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
