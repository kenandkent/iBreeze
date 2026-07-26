import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Typography, Button, List, Alert } from "antd";
import { UnlockOutlined } from "@ant-design/icons";
import { listOfflineProfiles, openProfile } from "../shared/tauriClient";
import { useAuthStore } from "../stores/authStore";
import type { OfflineProfile } from "../shared/tauriClient";

const { Title } = Typography;

export default function OfflineUnlockPage() {
  const [profiles, setProfiles] = useState<OfflineProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const navigate = useNavigate();
  const openProfileStore = useAuthStore((s) => s.openProfile);

  useEffect(() => {
    listOfflineProfiles()
      .then((r) => setProfiles(r.profiles))
      .catch(() => setError("无法加载离线 Profile"))
      .finally(() => setListLoading(false));
  }, []);

  const handleOpen = async (profile: OfflineProfile) => {
    setLoading(true);
    setError(null);
    try {
      const result = await openProfile(profile.profile_directory_id);
      openProfileStore({
        profileDirectoryId: result.profile_directory_id,
        maskedIdentifier: profile.masked_identifier,
        mode: result.mode,
        catalogReleaseSequence: result.catalog_release_sequence,
      });
      navigate("/dashboard", { replace: true });
    } catch (e) {
      const err = e as Record<string, unknown>;
      setError((err?.error as string) || (e instanceof Error ? e.message : "打开 Profile 失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center", background: "#f0f2f5" }}>
      <Card style={{ width: 480 }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <Title level={3} style={{ marginBottom: 4 }}>离线解锁</Title>
          <Typography.Text type="secondary">选择一个离线 Profile 打开</Typography.Text>
        </div>
        {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} />}
        <List
          loading={listLoading}
          dataSource={profiles}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key="open" type="primary" icon={<UnlockOutlined />} loading={loading} onClick={() => handleOpen(item)}>
                  打开
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={item.masked_identifier}
                description={`${item.backend_origin} · 过期: ${new Date(item.expires_at).toLocaleDateString()}`}
              />
            </List.Item>
          )}
          locale={{ emptyText: "没有可用的离线 Profile" }}
        />
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <Button type="link" onClick={() => navigate("/login")}>使用在线登录</Button>
        </div>
      </Card>
    </div>
  );
}
