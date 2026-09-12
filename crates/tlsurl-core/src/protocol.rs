//! Validated wire configuration shared by both language bindings.
use crate::Error;
use serde::Deserialize;
use wreq::{
    ClientBuilder,
    http2::{Http2Options, PseudoId, PseudoOrder},
    tls::{AlpnProtocol, TlsOptions, TlsVersion},
};

fn invalid(message: &str) -> Error {
    Error {
        code: "INVALID_CONFIG",
        message: message.into(),
    }
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct TlsConfig {
    min_version: Option<String>,
    max_version: Option<String>,
    alpn: Option<Vec<String>>,
    cipher_list: Option<String>,
    curves_list: Option<String>,
    sigalgs_list: Option<String>,
    grease: Option<bool>,
    permute_extensions: Option<bool>,
    sni: Option<bool>,
}

fn version(value: &str) -> Result<(u8, TlsVersion), Error> {
    match value {
        "1.0" => Ok((0, TlsVersion::TLS_1_0)),
        "1.1" => Ok((1, TlsVersion::TLS_1_1)),
        "1.2" => Ok((2, TlsVersion::TLS_1_2)),
        "1.3" => Ok((3, TlsVersion::TLS_1_3)),
        _ => Err(invalid("TLS version must be 1.0, 1.1, 1.2 or 1.3")),
    }
}

impl TlsConfig {
    pub fn apply(
        self,
        mut builder: ClientBuilder,
        base: Option<TlsOptions>,
    ) -> Result<ClientBuilder, Error> {
        let min = self.min_version.as_deref().map(version).transpose()?;
        let max = self.max_version.as_deref().map(version).transpose()?;
        if min.zip(max).is_some_and(|(min, max)| min.0 > max.0) {
            return Err(invalid("TLS minimum version exceeds maximum version"));
        }
        let mut options = base.unwrap_or_default();
        options.min_tls_version = min.map(|v| v.1).or(options.min_tls_version);
        options.max_tls_version = max.map(|v| v.1).or(options.max_tls_version);
        options.cipher_list = self.cipher_list.map(Into::into).or(options.cipher_list);
        options.curves_list = self.curves_list.map(Into::into).or(options.curves_list);
        options.sigalgs_list = self.sigalgs_list.map(Into::into).or(options.sigalgs_list);
        options.grease_enabled = self.grease.or(options.grease_enabled);
        options.permute_extensions = self.permute_extensions.or(options.permute_extensions);
        if let Some(protocols) = self.alpn {
            let protocols = protocols
                .iter()
                .map(|value| match value.as_str() {
                    "h2" => Ok(AlpnProtocol::HTTP2),
                    "http/1.1" => Ok(AlpnProtocol::HTTP1),
                    _ => Err(invalid("ALPN supports only h2 and http/1.1")),
                })
                .collect::<Result<Vec<_>, _>>()?;
            options.alpn_protocols = Some(protocols.into());
        }
        if let Some(sni) = self.sni {
            builder = builder.tls_sni(sni);
        }
        Ok(builder.tls_options(options))
    }
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Http2Config {
    initial_window_size: Option<u32>,
    initial_connection_window_size: Option<u32>,
    max_frame_size: Option<u32>,
    max_header_list_size: Option<u32>,
    header_table_size: Option<u32>,
    enable_push: Option<bool>,
    pseudo_order: Option<Vec<String>>,
}

impl Http2Config {
    pub fn apply(
        self,
        builder: ClientBuilder,
        base: Option<Http2Options>,
    ) -> Result<ClientBuilder, Error> {
        if self.initial_window_size.is_some_and(|n| n > 0x7fff_ffff)
            || self
                .initial_connection_window_size
                .is_some_and(|n| !(65535..=0x7fff_ffff).contains(&n))
        {
            return Err(invalid("HTTP/2 window sizes exceed allowed ranges"));
        }
        if self
            .max_frame_size
            .is_some_and(|n| !(16384..=16777215).contains(&n))
        {
            return Err(invalid(
                "HTTP/2 max_frame_size must be 16384 through 16777215",
            ));
        }
        let mut options = base.unwrap_or_else(|| Http2Options::builder().build());
        if let Some(n) = self.initial_window_size {
            options.initial_window_size = n;
        }
        if let Some(n) = self.initial_connection_window_size {
            options.initial_conn_window_size = n;
        }
        if let Some(n) = self.max_frame_size {
            options.max_frame_size = Some(n);
        }
        if let Some(n) = self.max_header_list_size {
            options.max_header_list_size = Some(n);
        }
        if let Some(n) = self.header_table_size {
            options.header_table_size = Some(n);
        }
        if let Some(enabled) = self.enable_push {
            options.enable_push = Some(enabled);
        }
        if let Some(names) = self.pseudo_order {
            let mut unique = names.clone();
            unique.sort();
            unique.dedup();
            if unique.len() != 4 || names.len() != 4 {
                return Err(invalid(
                    "pseudo_order must contain method, scheme, authority and path exactly once",
                ));
            }
            let order = names
                .iter()
                .map(|value| match value.as_str() {
                    "method" => Ok(PseudoId::Method),
                    "scheme" => Ok(PseudoId::Scheme),
                    "authority" => Ok(PseudoId::Authority),
                    "path" => Ok(PseudoId::Path),
                    _ => Err(invalid("unknown HTTP/2 pseudo header")),
                })
                .collect::<Result<Vec<_>, _>>()?;
            options.headers_pseudo_order = Some(PseudoOrder::builder().extend(order).build());
        }
        Ok(builder.http2_options(options))
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdentityConfig {
    certificate_pem: String,
    private_key_pem: String,
}

impl IdentityConfig {
    pub fn apply(self, builder: ClientBuilder) -> Result<ClientBuilder, Error> {
        Ok(
            builder.tls_identity(wreq::tls::trust::Identity::from_pkcs8_pem(
                self.certificate_pem.as_bytes(),
                self.private_key_pem.as_bytes(),
            )?),
        )
    }
}
