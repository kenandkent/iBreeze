import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tag, message, Modal, Form, Input } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface Item { capability_id: string; name: string; description: string; status: string; current_version: number; created_at: string; }
const sc: Record<string, string> = { draft: 'default', review: 'processing', published: 'success', deprecated: 'warning', archived: 'default' };

export default function CapabilityList() {
  const ref = useRef<ActionType>();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [form] = Form.useForm();

  const cols: ProColumns<Item>[] = [
    { title: '名称', dataIndex: 'name', width: 200 },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 100, render: (_, r) => <Tag color={sc[r.status]}>{r.status}</Tag> },
    { title: '版本', dataIndex: 'current_version', width: 80 },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 280,
      render: (_, r) => [
        <a key="e" onClick={() => { setEditing(r); form.setFieldsValue({ name: r.name, description: r.description }); setOpen(true); }}>编辑</a>,
        r.status === 'draft' && <a key="r" onClick={() => transition(r.capability_id, 'submit-review')}>提交审核</a>,
        r.status === 'review' && <a key="p" onClick={() => transition(r.capability_id, 'publish')}>发布</a>,
        r.status === 'published' && <a key="d" onClick={() => transition(r.capability_id, 'deprecate')}>弃用</a>,
        r.status === 'deprecated' && <a key="a" onClick={() => transition(r.capability_id, 'archive')}>归档</a>,
      ].filter(Boolean),
    },
  ];

  const transition = async (id: string, act: string) => { try { await api.post(`/capabilities/${id}/${act}`); message.success('操作成功'); ref.current?.reload(); } catch { message.error('操作失败'); } };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.put(`/capabilities/${editing.capability_id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/capabilities', { ...values, company_id: 'default' });
        message.success('创建成功');
      }
      setOpen(false); setEditing(null); form.resetFields();
      ref.current?.reload();
    } catch { message.error('操作失败'); }
  };

  return (
    <>
      <ProTable<Item> headerTitle="能力列表" actionRef={ref} rowKey="capability_id" columns={cols}
        request={async (p) => { const { data } = await api.get('/capabilities', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>新建能力</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title={editing ? '编辑能力' : '新建能力'} open={open} onOk={handleSubmit} onCancel={() => { setOpen(false); setEditing(null); }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
