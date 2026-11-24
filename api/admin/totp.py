"""TOTP 2FA for staff: secret generation (encrypted at rest), QR code, verification with replay protection,
single-use backup codes (hashed)."""
import secrets
import time

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken

from auth.security import sha256
from settings import get_settings

BACKUP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o/1/l/i
BACKUP_COUNT = 10


class NotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().admin_secret_key
    if not key:
        raise NotConfigured("AIWAZZ_ADMIN_SECRET_KEY is not set (manage.py gen-admin-key)")
    return Fernet(key.encode())


def new_secret() -> str:
    return pyotp.random_base32(32)      # 160 bits


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise NotConfigured("TOTP secret can't be decrypted (AIWAZZ_ADMIN_SECRET_KEY changed?)") from e


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().totp_issuer)


def qr_svg(uri: str) -> str:
    """Inline SVG (no external QR service: the secret never leaves the server except to the staff member)."""
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#070D25", light="#FFFFFF")


def verify(secret: str, code: str, last_step: int) -> int | None:
    """Return the matched time step if `code` is valid (±1 step for clock drift) and newer than last_step, else None."""
    code = "".join(c for c in code if c.isdigit())
    if len(code) != 6:
        return None
    t = pyotp.TOTP(secret)
    now_step = int(time.time()) // 30
    for step in (now_step - 1, now_step, now_step + 1):
        if step > last_step and secrets.compare_digest(t.generate_otp(step), code):
            return step
    return None


def new_backup_codes() -> list[str]:
    out = []
    for _ in range(BACKUP_COUNT):
        raw = "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(10))
        out.append(f"{raw[:5]}-{raw[5:]}")
    return out


def normalize_backup(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def backup_hash(code: str) -> str:
    return sha256("backup:" + normalize_backup(code))


def looks_like_backup(code: str) -> bool:
    return len(normalize_backup(code)) == 10 and not normalize_backup(code).isdigit()
