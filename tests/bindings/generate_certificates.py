"""Regenerate public test-only certificates (requires cryptography). Never use these keys outside tests."""
from datetime import datetime, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

ROOT = Path(__file__).with_name("certs")


def name(common_name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def builder(subject, issuer, key):
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime(2020, 1, 1, tzinfo=timezone.utc))
            .not_valid_after(datetime(2040, 1, 1, tzinfo=timezone.utc)))


def main():
    ROOT.mkdir(exist_ok=True)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = name("tlsurl public test CA")
    ca = (builder(ca_name, ca_name, ca_key)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    (ROOT / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for role, usage in (("server", ExtendedKeyUsageOID.SERVER_AUTH), ("client", ExtendedKeyUsageOID.CLIENT_AUTH)):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        certificate = (builder(name(f"tlsurl test {role}"), ca_name, key)
                       .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                       .add_extension(x509.ExtendedKeyUsage([usage]), critical=False))
        if role == "server":
            certificate = certificate.add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        certificate = certificate.sign(ca_key, hashes.SHA256())
        (ROOT / f"{role}.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        (ROOT / f"{role}-key.pem").write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    print("Generated public test-only certificates; CA private key is not retained")


if __name__ == "__main__":
    main()
