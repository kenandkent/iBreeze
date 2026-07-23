/// 本地文件存储，用于桌面配置和数据
use std::path::PathBuf;

/// Store 类型别名，供 Tauri AppState 使用
pub type Store = LocalStore;

pub struct LocalStore {
    base_path: PathBuf,
}

impl LocalStore {
    pub fn new(base_path: PathBuf) -> Self {
        Self { base_path }
    }

    pub fn get_config_path(&self) -> PathBuf {
        self.base_path.join("config.json")
    }

    pub fn get_data_path(&self) -> PathBuf {
        self.base_path.join("data")
    }

    pub fn ensure_directories(&self) -> Result<(), String> {
        std::fs::create_dir_all(&self.base_path)
            .map_err(|e| format!("Failed to create directories: {e}"))?;
        std::fs::create_dir_all(self.get_data_path())
            .map_err(|e| format!("Failed to create data directory: {e}"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env::temp_dir;

    #[test]
    fn test_local_store_paths() {
        let store = LocalStore::new(temp_dir().join("ibreeze_test"));
        assert!(store.get_config_path().ends_with("config.json"));
        assert!(store.get_data_path().ends_with("data"));
    }

    #[test]
    fn test_ensure_directories() {
        let store = LocalStore::new(temp_dir().join("ibreeze_test_dirs"));
        assert!(store.ensure_directories().is_ok());
        assert!(store.base_path.exists());
        assert!(store.get_data_path().exists());

        // Cleanup
        let _ = std::fs::remove_dir_all(&store.base_path);
    }
}
