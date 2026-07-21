import { useRef, useState } from 'react';
import { ProTable, type ActionType, type ProColumns } from '@ant-design/pro-components';
import { Button, Tag, message, Popconfirm, Modal, Form, Input, Select } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import api from '../../services/api';

interface GovRule { rule_id: string; name: string; category: string; action: string; enabled: number; created_at: string; }

export default function KnowledgeGovernance() {
  const ref = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<GovRule | null>(null);
  const [form] = Form.useForm();
  const cols: ProColumns<GovRule>[] = [
    { title: '规则名称', dataIndex: 'name', width: 200 },
    { title: '分类', dataIndex: 'category', width: 120 },
    { title: '动作', dataIndex: 'action', width: 120, render: (_, r) => <Tag color={r.action === 'auto_approve' ? 'success' : r.action === 'manual_review' ? 'processing' : 'warning'}>{r.action}</Tag> },
    { title: '启用', dataIndex: 'enabled', width: 80, render: (_, r) => <Tag color={r.enabled ? 'success' : 'default'}>{r.enabled ? '是' : '否'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, valueType: 'dateTime' },
    {
      title: '操作', valueType: 'option', width: 150,
      render: (_, r) => [
        <a key="e" onClick={() => { setEditing(r); form.setFieldsValue({ name: r.name, category: r.category, action: r.action }); setModalOpen(true); }}>编辑</a>,
        <Popconfirm key="d" title="确定删除?" onConfirm={() => del(r.rule_id)}><a>删除</a></Popconfirm>,
      ],
    },
  ];
  const del = async (id: string) => { try { await api.delete(`/governance/knowledge-rules/${id}`); message.success('已删除'); ref.current?.reload(); } catch { message.error('删除失败'); } };
  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) {
        await api.put(`/governance/knowledge-rules/${editing.rule_id}`, values);
        message.success('更新成功');
      } else {
        await api.post('/governance/knowledge-rules', { company_id: 'default', ...values });
        message.success('创建成功');
      }
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      ref.current?.reload();
    } catch { message.error(editing ? '更新失败' : '创建失败'); }
  };
  return (
    <>
      <ProTable<GovRule> headerTitle="知识治理规则" actionRef={ref} rowKey="rule_id" columns={cols}
        request={async (p) => { try { const { data } = await api.get('/governance/knowledge-rules', { params: { skip: (p.current! - 1) * p.pageSize!, limit: p.pageSize } }); return { data, success: true, total: data.length }; } catch { return { data: [], success: true, total: 0 }; } }}
        toolBarRender={() => [<Button key="a" type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true); }}>新建规则</Button>]}
        pagination={{ defaultPageSize: 20 }}
      />
      <Modal title={editing ? '编辑规则' : '新建规则'} open={modalOpen} onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields(); }} onOk={handleSubmit} destroyOnClose>
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="category" label="分类"><Input /></Form.Item>
          <Form.Item name="action" label="动作" rules={[{ required: true }]}>
            <Select options={[{ value: 'auto_approve', label: '自动审批' }, { value: 'manual_review', label: '人工审核' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
