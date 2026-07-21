import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tag, message, Modal, Form, Input } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface Item { template_id: string; name: string; role: string; status: string; version: string; created_at: string; }

export default function TemplateList() {
  const ref = useRef<ActionType>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [form] = Form.useForm();

  const cols: ProColumns<Item>[] = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '角色', dataIndex: 'role', width: 150 },
    { title: '状态', dataIndex: 'status', width: 100, render: (_, r) => <Tag color={r.status === 'active' ? 'success' : 'default'}>{r.status}</Tag> },
    { title: '版本', dataIndex: 'version', width: 80 },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 200,
      render: (_, r) => [
        <a key="e" onClick={() => { setEditing(r); form.setFieldsValue({ name: r.name, role: r.role }); setOpen(true); }}>编辑</a>,
        r.status === 'draft' && <a key="a" onClick={() => transition(r.template_id, 'activate')}>激活</a>,
        r.status === 'active' && <a key="c" onClick={() => transition(r.template_id, 'archive')}>归档</a>,
      ].filter(Boolean),
    },
  ];

  const transition = async (id: string, act: string) => { try { await api.post(`/templates/${id}/${act}`); message.success('操作成功'); ref.current?.reload(); } catch { message.error('操作失败'); } };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.put(`/templates/${editing.template_id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/templates', values);
        message.success('创建成功');
      }
      setOpen(false); setEditing(null); form.resetFields();
      ref.current?.reload();
    } catch { message.error('操作失败'); }
  };

  return (
    <>
      <ProTable<Item> headerTitle="员工模板" actionRef={ref} rowKey="template_id" columns={cols}
        request={async (p) => { const { data } = await api.get('/templates', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新建模板</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title={editing ? '编辑模板' : '新建模板'} open={open} onOk={handleSubmit} onCancel={() => { setOpen(false); setEditing(null); }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
