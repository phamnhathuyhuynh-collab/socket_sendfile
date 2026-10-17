"""TLS identity, certificate pinning and safe relative path handling."""
from __future__ import annotations

import hashlib
import ipaddress
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


class SecurityError(ValueError):
    pass


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "retrotransfer98"


def ensure_certificates(folder: str | Path) -> tuple[Path, Path, str]:
    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    key_file, cert_file = folder / "identity.key", folder / "identity.crt"
    if key_file.exists() != cert_file.exists():
        raise SecurityError("An incomplete TLS certificate/key pair was found. Check the certificate directory.")
    if not key_file.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RetroTransfer98 local server")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
            ]), critical=False)
            .sign(key, hashes.SHA256())
        )
        # Use an exclusive create to avoid accidentally truncating an existing key.
        fd = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
        cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    else:
        # Warn through failure when a key is readable by other local users on POSIX.
        if os.name == "posix":
            mode = key_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise SecurityError("The private key has unsafe permissions. Run: chmod 600 " + str(key_file))
    cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
    return cert_file, key_file, cert.fingerprint(hashes.SHA256()).hex().upper()


def fingerprint_of_der(cert_der: bytes) -> str:
    return hashlib.sha256(cert_der).hexdigest().upper()


def normalize_fingerprint(text: str) -> str:
    cleaned = text.strip().replace(":", "").replace(" ", "").upper()
    if len(cleaned) != 64 or any(c not in "0123456789ABCDEF" for c in cleaned):
        raise SecurityError("The fingerprint must contain 64 SHA-256 hexadecimal characters (colons are allowed).")
    return cleaned


def relative_parts(raw: str, allow_root: bool = False) -> tuple[str, ...]:
    if not isinstance(raw, str):
        raise SecurityError("Invalid path.")
    if raw in ("", ".") and allow_root:
        return ()
    if not raw or len(raw) > 1024 or raw.startswith("/") or raw.endswith("/"):
        raise SecurityError("The path is empty, absolute, or too long.")
    parts = raw.split("/")
    if len(parts) > 64 or any(p in ("", ".", "..") for p in parts):
        raise SecurityError("The path contains an invalid component.")
    # Strictly portable subset; block Windows separators/drives and control chars.
    if any(any(ch in '\\:<>|?*\x00' or ord(ch) < 32 for ch in part) for part in parts):
        raise SecurityError("The path contains a forbidden character.")
    if any(p.endswith((" ", ".")) for p in parts):
        raise SecurityError("Names ending with a space or period are not supported.")
    return tuple(parts)


def safe_path(root: str | Path, relative: str, *, allow_root: bool = False,
              forbidden_dir: str | Path | None = None) -> Path:
    """Resolve a path below root; reject .., absolute paths and existing symlinks.

    This is not protection against a malicious local process racing to change symlinks.
    """
    base = Path(root).expanduser().resolve(strict=True)
    parts = relative_parts(relative, allow_root=allow_root)
    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise SecurityError("Symbolic links are not allowed: " + part)
    result = current.resolve(strict=False)
    if not result.is_relative_to(base):
        raise SecurityError("The path escapes the shared directory.")
    if forbidden_dir:
        forbidden = Path(forbidden_dir).expanduser().resolve(strict=False)
        if result == forbidden or result.is_relative_to(forbidden):
            raise SecurityError("Access to the TLS key directory is not allowed.")
    return result


def safe_remote_join(a: str, b: str) -> str:
    """Combine protocol paths after validating both."""
    relative_parts(a, allow_root=True)
    relative_parts(b)
    combined = f"{a}/{b}" if a not in ("", ".") else b
    relative_parts(combined)
    return combined
