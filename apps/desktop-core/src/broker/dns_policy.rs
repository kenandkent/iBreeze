use std::net::{IpAddr, Ipv6Addr};

use url::Url;

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct DnsPolicy {
    pub allow_loopback: bool,
    pub max_redirects: u32,
}

impl DnsPolicy {
    pub fn new() -> Self {
        Self {
            allow_loopback: false,
            max_redirects: 5,
        }
    }

    pub fn permit_loopback(mut self) -> Self {
        self.allow_loopback = true;
        self
    }

    pub fn validate_url(&self, url_str: &str) -> Result<(), AppError> {
        let url = Url::parse(url_str)
            .map_err(|e| AppError::Security(format!("SSRF guard: invalid URL: {e}")))?;

        if url.scheme() != "https" {
            return Err(AppError::Security(format!(
                "SSRF guard: scheme '{}' is not allowed; only HTTPS",
                url.scheme()
            )));
        }

        if url.username() != "" || url.password().is_some() {
            return Err(AppError::Security("SSRF guard: userinfo is not allowed".to_owned()));
        }

        if url.fragment().is_some() {
            return Err(AppError::Security("SSRF guard: fragment is not allowed".to_owned()));
        }

        let host = url
            .host_str()
            .ok_or_else(|| AppError::Security("SSRF guard: URL has no host".to_owned()))?;

        if let Some(port) = url.port() {
            if port != 443 {
                return Err(AppError::Security(format!(
                    "SSRF guard: non-standard port {port} is not allowed"
                )));
            }
        }

        let normalized = host.to_ascii_lowercase();
        if let Ok(ip) = normalized.parse::<IpAddr>() {
            if self.is_forbidden_address(&ip) {
                return Err(AppError::Security(format!(
                    "SSRF guard: address {ip} is forbidden"
                )));
            }
        }

        Ok(())
    }

    pub fn is_forbidden_address(&self, ip: &IpAddr) -> bool {
        if self.allow_loopback && is_loopback(ip) {
            return false;
        }
        is_private_ip(ip)
            || is_loopback(ip)
            || is_link_local(ip)
            || is_multicast(ip)
            || is_reserved(ip)
            || ip.is_unspecified()
    }

    pub async fn resolve_and_validate(
        &self,
        host: &str,
    ) -> Result<Vec<IpAddr>, AppError> {
        if let Ok(ip) = host.parse::<IpAddr>() {
            if self.is_forbidden_address(&ip) {
                return Err(AppError::Security(format!(
                    "SSRF guard: address {ip} is forbidden"
                )));
            }
            return Ok(vec![ip]);
        }
        let addrs = tokio::net::lookup_host((host, 443))
            .await
            .map_err(|e| AppError::Network(format!("DNS resolution failed for {host}: {e}")))?;
        let ips: Vec<IpAddr> = addrs.map(|a| a.ip()).collect();
        if ips.is_empty() {
            return Err(AppError::Network(format!(
                "DNS resolution returned no addresses for {host}"
            )));
        }
        for ip in &ips {
            if self.is_forbidden_address(ip) {
                return Err(AppError::Security(format!(
                    "SSRF guard: resolved address {ip} for '{host}' is forbidden"
                )));
            }
        }
        Ok(ips)
    }
}

impl Default for DnsPolicy {
    fn default() -> Self {
        Self::new()
    }
}

fn is_private_ip(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 10
                || (o[0] == 172 && o[1] >= 16 && o[1] <= 31)
                || (o[0] == 192 && o[1] == 168)
        }
        IpAddr::V6(v6) => v6.octets()[0] == 0xfc || v6.octets()[0] == 0xfd,
    }
}

fn is_loopback(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => v4.octets()[0] == 127,
        IpAddr::V6(v6) => *v6 == Ipv6Addr::LOCALHOST,
    }
}

fn is_link_local(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 169 && o[1] == 254
        }
        IpAddr::V6(v6) => {
            let o = v6.octets();
            o[0] == 0xfe && (o[1] & 0xc0) == 0x80
        }
    }
}

fn is_multicast(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => v4.octets()[0] & 0xf0 == 0xe0,
        IpAddr::V6(v6) => v6.octets()[0] == 0xff,
    }
}

fn is_reserved(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 0
                || o[0] == 100 && (o[1] & 0xc0) == 0x40
                || o[0] == 198 && (o[1] & 0xfe) == 0x18
                || o[0] == 192 && o[1] == 0 && o[2] == 0
                || o[0] == 203 && o[1] == 0 && o[2] == 113
                || o[0] >= 224
        }
        IpAddr::V6(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Ipv4Addr;

    #[test]
    fn rejects_non_https_scheme() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("http://example.com/api").is_err());
        assert!(policy.validate_url("ftp://example.com").is_err());
        assert!(policy.validate_url("file:///etc/passwd").is_err());
    }

    #[test]
    fn accepts_https() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://api.example.com/v1/chat").is_ok());
    }

    #[test]
    fn rejects_userinfo() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://user:pass@api.example.com/").is_err());
    }

    #[test]
    fn rejects_fragment() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://api.example.com/path#frag").is_err());
    }

    #[test]
    fn rejects_non_standard_port() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://api.example.com:8080/path").is_err());
    }

    #[test]
    fn accepts_standard_port() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://api.example.com:443/path").is_ok());
    }

    #[test]
    fn forbids_private_ipv4() {
        assert!(is_private_ip(&IpAddr::V4(Ipv4Addr::new(10, 0, 0, 1))));
        assert!(is_private_ip(&IpAddr::V4(Ipv4Addr::new(172, 16, 0, 1))));
        assert!(is_private_ip(&IpAddr::V4(Ipv4Addr::new(192, 168, 1, 1))));
        assert!(!is_private_ip(&IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
    }

    #[test]
    fn forbids_loopback() {
        assert!(is_loopback(&IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1))));
        assert!(is_loopback(&IpAddr::V6(Ipv6Addr::LOCALHOST)));
        assert!(!is_loopback(&IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
    }

    #[test]
    fn forbids_link_local() {
        assert!(is_link_local(&IpAddr::V4(Ipv4Addr::new(169, 254, 1, 1))));
        assert!(!is_link_local(&IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
    }

    #[test]
    fn forbids_multicast() {
        assert!(is_multicast(&IpAddr::V4(Ipv4Addr::new(224, 0, 0, 1))));
        assert!(is_multicast(&IpAddr::V6(Ipv6Addr::new(0xff00, 0, 0, 0, 0, 0, 0, 0))));
    }

    #[test]
    fn forbids_ip_literal() {
        let policy = DnsPolicy::new();
        assert!(policy.validate_url("https://127.0.0.1/api").is_err());
        assert!(policy.validate_url("https://10.0.0.1/api").is_err());
        assert!(policy.validate_url("https://169.254.169.254/").is_err());
    }

    #[test]
    fn permit_loopback_allows_localhost() {
        let policy = DnsPolicy::new().permit_loopback();
        assert!(policy.validate_url("https://127.0.0.1:443/api").is_ok());
    }

    #[test]
    fn is_forbidden_address_checks_all_categories() {
        let policy = DnsPolicy::new();
        assert!(policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(0, 0, 0, 0))));
        assert!(policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1))));
        assert!(policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(10, 0, 0, 1))));
        assert!(policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(169, 254, 1, 1))));
        assert!(policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(224, 0, 0, 1))));
        assert!(!policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
        assert!(!policy.is_forbidden_address(&IpAddr::V4(Ipv4Addr::new(1, 1, 1, 1))));
    }
}
