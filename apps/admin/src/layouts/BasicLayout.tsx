import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-components';
import { LogoutOutlined } from '@ant-design/icons';
import { Button, Popconfirm } from 'antd';
import {
  ToolOutlined, FileTextOutlined, TeamOutlined,
  BookOutlined, ApiOutlined, SafetyCertificateOutlined,
  AuditOutlined,
} from '@ant-design/icons';

const routes = {
  routes: [
    { name: '能力管理', icon: <ToolOutlined />, routes: [
      { path: '/capabilities', name: 'Capability 列表' },
      { path: '/skills', name: '技能列表' },
      { path: '/prompts', name: 'Prompt 资产' },
      { path: '/templates', name: '员工模板' },
      { path: '/capability-engine', name: '能力引擎' },
    ]},
    { name: '知识管理', icon: <BookOutlined />, routes: [
      { path: '/knowledge', name: '知识库' },
      { path: '/knowledge/governance', name: '知识治理' },
    ]},
    { path: '/providers', name: 'Provider 与 Backend', icon: <ApiOutlined /> },
    { path: '/governance', name: '治理与审批', icon: <SafetyCertificateOutlined /> },
    { name: '审计', icon: <AuditOutlined />, routes: [
      { path: '/audit', name: '审计日志' },
      { path: '/audit/interventions', name: '人工干预' },
    ]},
  ],
};

export default function BasicLayout() {
  const navigate = useNavigate();
  const loc = useLocation();
  return (
    <ProLayout
      title="iBreeze Admin"
      logo={false}
      route={routes}
      location={{ pathname: loc.pathname }}
      menuItemRender={(item, dom) => (
        <a onClick={() => item.path && navigate(item.path)}>{dom}</a>
      )}
      actionsRender={() => [
        <Popconfirm key="logout" title="确定退出?" onConfirm={() => {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          navigate('/login');
        }}>
          <Button type="text" icon={<LogoutOutlined />}>退出</Button>
        </Popconfirm>
      ]}
    >
      <Outlet />
    </ProLayout>
  );
}
