/// 安全密钥环，用于存储 API 密钥和令牌
use std::collections::HashMap;
use std::sync::Mutex;

/// Keyring 类型别名，供 Tauri AppState 使用
pub type Keyring = SecureKeyring;

pub struct SecureKeyring {
    keys: Mutex<HashMap<String, String>>,
}

impl SecureKeyring {
    pub fn new() -> Self {
        Self {
            keys: Mutex::new(HashMap::new()),
        }
    }

    pub fn set(&self, key: &str, value: &str) -> Result<(), String> {
        let mut lock = self.keys.lock().map_err(|e| e.to_string())?;
        lock.insert(key.to_string(), value.to_string());
        Ok(())
    }

    pub fn get(&self, key: &str) -> Result<Option<String>, String> {
        let lock = self.keys.lock().map_err(|e| e.to_string())?;
        Ok(lock.get(key).cloned())
    }

    pub fn delete(&self, key: &str) -> Result<bool, String> {
        let mut lock = self.keys.lock().map_err(|e| e.to_string())?;
        Ok(lock.remove(key).is_some())
    }

    pub fn list_keys(&self) -> Result<Vec<String>, String> {
        let lock = self.keys.lock().map_err(|e| e.to_string())?;
        Ok(lock.keys().cloned().collect())
    }
}

impl Default for SecureKeyring {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_keyring_set_and_get() {
        let keyring = SecureKeyring::new();
        keyring.set("api_key", "secret123").unwrap();
        assert_eq!(keyring.get("api_key").unwrap(), Some("secret123".to_string()));
    }

    #[test]
    fn test_keyring_delete() {
        let keyring = SecureKeyring::new();
        keyring.set("api_key", "secret123").unwrap();
        assert!(keyring.delete("api_key").unwrap());
        assert_eq!(keyring.get("api_key").unwrap(), None);
    }

    #[test]
    fn test_keyring_list_keys() {
        let keyring = SecureKeyring::new();
        keyring.set("key1", "val1").unwrap();
        keyring.set("key2", "val2").unwrap();
        let mut keys = keyring.list_keys().unwrap();
        keys.sort();
        assert_eq!(keys, vec!["key1", "key2"]);
    }
}
