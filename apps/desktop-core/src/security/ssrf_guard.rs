use url::Url;

use crate::error::AppError;

fn is_private_ip(ip: std::net::IpAddr) -> bool {
    match ip {
        std::net::IpAddr::V4(v4) => {
            let o = v4.octets();
            o[0] == 0
                || o[0] == 10
                || o[0] == 127
                || (o[0] == 169 && o[1] == 254)
                || (o[0] == 172 && o[1] >= 16 && o[1] <= 31)
                || (o[0] == 192 && o[1] == 168)
        }
        std::net::IpAddr::V6(v6) => {
            v6 == std::net::Ipv6Addr::LOCALHOST
                || v6 == std::net::Ipv6Addr::UNSPECIFIED
                || (v6.octets()[0] == 0xfe && (v6.octets()[1] & 0xc0) == 0x80)
                || v6.octets()[0] == 0xfc
                || v6.octets()[0] == 0xfd
        }
    }
}

async fn resolve_host(host: &str) -> Result<Vec<std::net::IpAddr>, AppError> {
    if let Ok(ip) = host.parse::<std::net::IpAddr>() {
        return Ok(vec![ip]);
    }
    let addrs = tokio::net::lookup_host((host, 0))
        .await
        .map_err(|e| {
            AppError::Network(format!("SSRF guard: DNS resolution failed for {host}: {e}"))
        })?;
    let ips: Vec<_> = addrs.map(|a| a.ip()).collect();
    if ips.is_empty() {
        return Err(AppError::Network(format!(
            "SSRF guard: DNS resolution returned no addresses for {host}"
        )));
    }
    Ok(ips)
}

pub async fn validate_outbound_url(
    url_str: &str,
    allowed_domains: &[String],
) -> Result<(), AppError> {
    let url = Url::parse(url_str)
        .map_err(|e| AppError::Security(format!("SSRF guard: invalid URL: {e}")))?;

    match url.scheme() {
        "file" | "ftp" | "gopher" => {
            return Err(AppError::Security(format!(
                "SSRF guard: scheme '{}' is not allowed for outbound requests",
                url.scheme()
            )));
        }
        _ => {}
    }

    let host = url.host_str().ok_or_else(|| {
        AppError::Security("SSRF guard: URL has no host".to_owned())
    })?;

    if !allowed_domains.is_empty() {
        let is_allowed = allowed_domains
            .iter()
            .any(|d| host == d || host.ends_with(&format!(".{d}")));
        if !is_allowed {
            return Err(AppError::Security(format!(
                "SSRF guard: domain '{host}' is not in allowed domains"
            )));
        }
    }

    let ips = resolve_host(host).await?;
    for ip in &ips {
        if is_private_ip(*ip) {
            return Err(AppError::Security(format!(
                "SSRF guard: resolved address {ip} is a private/internal IP for host '{host}'"
            )));
        }
    }

    Ok(())
}

pub async fn validate_redirect_url(
    original_url: &str,
    redirect_url: &str,
    allowed_domains: &[String],
) -> Result<(), AppError> {
    if redirect_url == original_url {
        return Err(AppError::Security(
            "SSRF guard: redirect loop detected".to_owned(),
        ));
    }
    validate_outbound_url(redirect_url, allowed_domains).await
}
