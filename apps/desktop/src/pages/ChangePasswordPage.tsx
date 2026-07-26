import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Form, Input, Button, Card, Typography, Alert } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { changePassword } from "../shared/tauriClient";
import { useAuthStore } from "../stores/authStore";

const { Title } = Typography;

export default function ChangePasswordPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const openProfile = useAuthStore((s) => s.openProfile);
  const email = (location.state as { email?: string })?.email;

  const handleSubmit = async (values: { current_password: string; new_password: string }) => {
    setLoading(true);
    setError(null);
    try {
      const result = await changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      openProfile({
        profileDirectoryId: result.profile_directory_id,
        maskedIdentifier: result.masked_identifier,
        mode: "online",
        catalogReleaseSequence: result.catalog_release_sequence,
      });
      navigate("/dashboard", { replace: true });
    } catch (e) {
      const err = e as Record<string, unknown>;
      setError((err?.error as string) || (e instanceof Error ? e.message : "密码修改失败"));
    } finally {
      setLoading(false);
    }
  };

  if (!email) {
    navigate("/login", { replace: true });
    return null;
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", background: "#f0f2f5" }}>
      <Card style={{ width: 400 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>修改密码</Title>
          <Typography.Text type="secondary">首次登录需要修改密码</Typography.Text>
        </div>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={handleSubmit} autoComplete="off">
          <Form.Item name="current_password" rules={[{ required: true, message: "请输入当前密码" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="当前密码" size="large" />
          </Form.Item>
          <Form.Item name="new_password" rules={[{ required: true, message: "请输入新密码" }, { min: 8, message: "密码至少8位" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少8位）" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">确认修改</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
