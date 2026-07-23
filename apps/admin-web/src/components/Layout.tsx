import { useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout as AntLayout, Menu } from 'antd';
import {
  RobotOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  UserOutlined,
  SendOutlined,
  ApiOutlined,
  LinkOutlined,
  SettingOutlined,
  AuditOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../stores/authStore';

const { Sider, Content, Header } = AntLayout;

const MENU_ITEMS = [
  { key: '/agents', icon: <RobotOutlined />, label: 'Agent 管理' },
  { key: '/models', icon: <AppstoreOutlined />, label: '模型管理' },
  { key: '/providers', icon: <CloudServerOutlined />, label: '提供商管理' },
  { key: '/users', icon: <UserOutlined />, label: '用户管理' },
  { key: '/releases', icon: <SendOutlined />, label: '发布管理' },
  { key: '/skills', icon: <ApiOutlined />, label: 'Skill 管理' },
  { key: '/compatibility', icon: <LinkOutlined />, label: '兼容性规则' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  { key: '/audit-logs', icon: <AuditOutlined />, label: '审计日志' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth={0}>
        <div style={{ padding: '16px', color: '#fff', fontSize: 18, fontWeight: 'bold' }}>
          iBreeze Admin
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <LogoutOutlined
            style={{ fontSize: 16, cursor: 'pointer' }}
            onClick={() => { logout(); navigate('/login', { replace: true }); }}
          />
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
