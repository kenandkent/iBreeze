import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Form, Input, Button, Card, Typography, Alert } from "antd";
import { CloudServerOutlined } from "@ant-design/icons";
import { validateOrigin } from "../shared/tauriClient";
import { logger } from "../utils/logger";

const { Title } = Typography;

export default function ServerPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSubmit = async (values: { origin: string }) => {
    setLoading(true);
    setError(null);
    try {
      const result = await validateOrigin(values.origin);
      if (result.valid) {
        logger.info("ServerPage", "origin_valid", { origin: result.canonical_origin });
        navigate("/login", { state: { canonicalOrigin: result.canonical_origin, appUserId: result.app_user_id } });
      } else {
        setError("服务器地址无效，请检查后重试");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "无法连接服务器");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", background: "#f0f2f5" }}>
      <Card style={{ width: 400 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>iBreeze</Title>
          <Typography.Text type="secondary">连接服务器</Typography.Text>
        </div>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={handleSubmit} autoComplete="off">
          <Form.Item name="origin" rules={[{ required: true, message: "请输入服务器地址" }]}>
            <Input prefix={<CloudServerOutlined />} placeholder="服务器地址 (https://example.com)" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">连接</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
