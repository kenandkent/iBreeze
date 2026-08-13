//! Persistent, secret-free idempotency records for credential mutations.
//!
//! The record stores only a request fingerprint and the non-sensitive
//! metadata response.  The secret is represented by an HMAC in the
//! fingerprint and is never written to this file or emitted to logs.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

use crate::error::AppError;

const TTL_HOURS: i64 = 24;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    key: Uuid,
    method: String,
    request_fingerprint: String,
    expires_at: DateTime<Utc>,
    response: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(deny_unknown_fields)]
struct FileFormat {
    schema_version: u8,
    records: Vec<Record>,
}

pub struct CredentialIdempotencyStore {
    path: PathBuf,
}

impl CredentialIdempotencyStore {
    pub fn new(profile_root: impl AsRef<Path>) -> Self {
        Self {
            path: profile_root.as_ref().join("credential-idempotency.v1.json"),
        }
    }

    pub fn lookup(
        &self,
        key: Uuid,
        method: &str,
        request_fingerprint: &str,
    ) -> Result<Option<Value>, AppError> {
        let mut file = self.load()?;
        let now = Utc::now();
        file.records.retain(|record| record.expires_at > now);
        let result = file
            .records
            .iter()
            .find(|record| record.key == key && record.method == method)
            .map(|record| {
                if record.request_fingerprint != request_fingerprint {
                    Err(AppError::Conflict("IDEMPOTENCY_CONFLICT".to_owned()))
                } else {
                    Ok(record.response.clone())
                }
            })
            .transpose()?;
        self.save(&file)?;
        Ok(result)
    }

    pub fn record(
        &self,
        key: Uuid,
        method: &str,
        request_fingerprint: &str,
        response: Value,
    ) -> Result<(), AppError> {
        let mut file = self.load()?;
        let now = Utc::now();
        file.records.retain(|record| record.expires_at > now);
        if let Some(existing) = file
            .records
            .iter_mut()
            .find(|record| record.key == key && record.method == method)
        {
            if existing.request_fingerprint != request_fingerprint {
                return Err(AppError::Conflict("IDEMPOTENCY_CONFLICT".to_owned()));
            }
            return Ok(());
        }
        file.records.push(Record {
            key,
            method: method.to_owned(),
            request_fingerprint: request_fingerprint.to_owned(),
            expires_at: now + Duration::hours(TTL_HOURS),
            response,
        });
        self.save(&file)
    }

    fn load(&self) -> Result<FileFormat, AppError> {
        if !self.path.exists() {
            return Ok(FileFormat {
                schema_version: 1,
                records: Vec::new(),
            });
        }
        let bytes = fs::read(&self.path).map_err(|error| AppError::Storage(error.to_string()))?;
        let file: FileFormat = serde_json::from_slice(&bytes)
            .map_err(|_| AppError::Security("CREDENTIAL_IDEMPOTENCY_CORRUPT".to_owned()))?;
        if file.schema_version != 1 {
            return Err(AppError::Security(
                "CREDENTIAL_IDEMPOTENCY_CORRUPT".to_owned(),
            ));
        }
        Ok(file)
    }

    fn save(&self, file: &FileFormat) -> Result<(), AppError> {
        let parent = self
            .path
            .parent()
            .ok_or_else(|| AppError::Storage("credential idempotency parent missing".to_owned()))?;
        fs::create_dir_all(parent).map_err(|error| AppError::Storage(error.to_string()))?;
        let temporary = self.path.with_extension("json.tmp");
        let bytes = serde_json::to_vec_pretty(file)
            .map_err(|error| AppError::Internal(error.to_string()))?;
        let mut handle = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .open(&temporary)
            .map_err(|error| AppError::Storage(error.to_string()))?;
        handle
            .write_all(&bytes)
            .map_err(|error| AppError::Storage(error.to_string()))?;
        handle
            .sync_all()
            .map_err(|error| AppError::Storage(error.to_string()))?;
        drop(handle);
        fs::rename(&temporary, &self.path).map_err(|error| AppError::Storage(error.to_string()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&self.path, fs::Permissions::from_mode(0o600))
                .map_err(|error| AppError::Storage(error.to_string()))?;
        }
        Ok(())
    }
}
