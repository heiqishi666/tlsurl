//! Randomize supported ClientHello parameters once per client, not TLS key material.
use crate::Error;
use wreq::tls::{TlsOptions, TlsVersion};

// Explicit algorithm keeps a supplied seed portable across languages and targets.
// This generator only selects public configuration; BoringSSL generates TLS secrets.
struct Sequence(u64);

impl Sequence {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }

    fn shuffle<T>(&mut self, values: &mut [T]) {
        for i in (1..values.len()).rev() {
            values.swap(i, (self.next() % (i as u64 + 1)) as usize);
        }
    }
}

pub fn options(seed: Option<u32>) -> Result<TlsOptions, Error> {
    let seed = match seed {
        Some(seed) => u64::from(seed),
        None => {
            let mut bytes = [0; 8];
            getrandom::fill(&mut bytes).map_err(|_| Error {
                code: "INVALID_CONFIG",
                message: "could not obtain randomness for TLS configuration".into(),
            })?;
            u64::from_le_bytes(bytes)
        }
    };
    let mut sequence = Sequence(seed);
    // Retain an AES-GCM suite for both RSA and ECDSA TLS 1.2 servers.
    let mut ciphers = vec![
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
    ];
    for cipher in [
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
    ] {
        if sequence.next() & 1 == 1 {
            ciphers.push(cipher);
        }
    }
    sequence.shuffle(&mut ciphers);
    let mut signatures = [
        "ecdsa_secp256r1_sha256",
        "ecdsa_secp384r1_sha384",
        "rsa_pss_rsae_sha256",
        "rsa_pss_rsae_sha384",
        "rsa_pkcs1_sha256",
        "rsa_pkcs1_sha384",
    ];
    sequence.shuffle(&mut signatures);
    let mut curves = ["X25519", "P-256", "P-384"];
    sequence.shuffle(&mut curves);
    let mut options = TlsOptions::default();
    options.min_tls_version = Some(TlsVersion::TLS_1_2);
    options.max_tls_version = Some(TlsVersion::TLS_1_3);
    options.cipher_list = Some(ciphers.join(":").into());
    options.sigalgs_list = Some(signatures.join(":").into());
    options.curves_list = Some(curves.join(":").into());
    options.permute_extensions = Some(false);
    options.grease_enabled = Some(true);
    options.aes_hw_override = Some(true);
    options.session_ticket = false;
    Ok(options)
}
