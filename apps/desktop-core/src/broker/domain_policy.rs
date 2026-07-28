use std::collections::BTreeSet;

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct DomainPolicy {
    allowlist: BTreeSet<NormalizedDomain>,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct NormalizedDomain(String);

impl NormalizedDomain {
    pub fn new(domain: &str) -> Self {
        Self(domain.to_ascii_lowercase())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl DomainPolicy {
    pub fn new(allowlist: BTreeSet<NormalizedDomain>) -> Self {
        Self { allowlist }
    }

    pub fn empty() -> Self {
        Self {
            allowlist: BTreeSet::new(),
        }
    }

    pub fn is_allowed(&self, host: &str) -> bool {
        if self.allowlist.is_empty() {
            return false;
        }
        let host = host.to_ascii_lowercase();
        self.allowlist
            .iter()
            .any(|allowed| matches_domain(&host, allowed.as_str()))
    }

    pub fn require_allowed(&self, host: &str) -> Result<(), AppError> {
        if self.is_allowed(host) {
            Ok(())
        } else {
            Err(AppError::Security(format!(
                "EGRESS_DOMAIN_DENIED: {host} is not in the allowlist"
            )))
        }
    }

    pub fn add_domain(&mut self, domain: &str) {
        self.allowlist.insert(NormalizedDomain::new(domain));
    }

    pub fn extend(&mut self, domains: impl IntoIterator<Item = String>) {
        for domain in domains {
            self.allowlist.insert(NormalizedDomain::new(&domain));
        }
    }

    pub fn allowlist(&self) -> &BTreeSet<NormalizedDomain> {
        &self.allowlist
    }

    pub fn is_empty(&self) -> bool {
        self.allowlist.is_empty()
    }

    pub fn len(&self) -> usize {
        self.allowlist.len()
    }
}

pub fn matches_domain(host: &str, pattern: &str) -> bool {
    let host = host.to_ascii_lowercase();
    let pattern = pattern.to_ascii_lowercase();

    if host == pattern {
        return true;
    }

    if let Some(wildcard_suffix) = pattern.strip_prefix("*.") {
        let dot_pos = host.find('.');
        match dot_pos {
            Some(pos) => {
                let suffix = &host[pos..];
                suffix == wildcard_suffix
                    && host.len() > suffix.len() + 1
                    && !host[..pos].contains('.')
            }
            None => false,
        }
    } else {
        false
    }
}

pub fn normalize_domain(domain: &str) -> String {
    domain.to_ascii_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_match() {
        assert!(matches_domain("api.example.com", "api.example.com"));
    }

    #[test]
    fn case_insensitive() {
        assert!(matches_domain("API.EXAMPLE.COM", "api.example.com"));
        assert!(matches_domain("api.example.com", "API.EXAMPLE.COM"));
    }

    #[test]
    fn wildcard_one_label() {
        assert!(matches_domain("api.example.com", "*.example.com"));
    }

    #[test]
    fn wildcard_rejects_two_labels() {
        assert!(!matches_domain("a.b.example.com", "*.example.com"));
    }

    #[test]
    fn wildcard_rejects_exact_without_sub() {
        assert!(!matches_domain("example.com", "*.example.com"));
    }

    #[test]
    fn wildcard_different_suffix() {
        assert!(!matches_domain("api.other.com", "*.example.com"));
    }

    #[test]
    fn domain_policy_empty_is_deny_all() {
        let policy = DomainPolicy::empty();
        assert!(policy.is_empty());
        assert!(!policy.is_allowed("example.com"));
        assert!(!policy.is_allowed("any.domain.com"));
    }

    #[test]
    fn domain_policy_exact_match() {
        let mut policy = DomainPolicy::empty();
        policy.add_domain("api.example.com");
        assert!(policy.is_allowed("api.example.com"));
        assert!(!policy.is_allowed("other.example.com"));
    }

    #[test]
    fn domain_policy_wildcard() {
        let mut policy = DomainPolicy::empty();
        policy.add_domain("*.example.com");
        assert!(policy.is_allowed("api.example.com"));
        assert!(policy.is_allowed("chat.example.com"));
        assert!(!policy.is_allowed("example.com"));
        assert!(!policy.is_allowed("deep.sub.example.com"));
    }

    #[test]
    fn domain_policy_multiple_entries() {
        let mut set = BTreeSet::new();
        set.insert(NormalizedDomain::new("api.openai.com"));
        set.insert(NormalizedDomain::new("*.anthropic.com"));
        let policy = DomainPolicy::new(set);
        assert!(policy.is_allowed("api.openai.com"));
        assert!(policy.is_allowed("api.anthropic.com"));
        assert!(!policy.is_allowed("other.com"));
    }

    #[test]
    fn require_allowed_returns_ok_or_error() {
        let mut policy = DomainPolicy::empty();
        policy.add_domain("allowed.com");
        assert!(policy.require_allowed("allowed.com").is_ok());
        assert!(policy.require_allowed("blocked.com").is_err());
    }

    #[test]
    fn extend_adds_multiple() {
        let mut policy = DomainPolicy::empty();
        policy.extend(vec!["a.com".to_owned(), "b.com".to_owned()]);
        assert_eq!(policy.len(), 2);
    }

    #[test]
    fn normalized_domain_order() {
        let mut set = BTreeSet::new();
        set.insert(NormalizedDomain::new("z.com"));
        set.insert(NormalizedDomain::new("a.com"));
        let ordered: Vec<_> = set.iter().map(|d| d.as_str().to_owned()).collect();
        assert_eq!(ordered, vec!["a.com", "z.com"]);
    }
}
