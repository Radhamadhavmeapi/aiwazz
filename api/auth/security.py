"""Passwords (argon2id), random tokens, invite codes and API keys. Only hashes are ever stored."""
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()  # argon2id, RFC 9106 defaults (64 MiB, t=3, p=4)
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))  # equalises timing for unknown emails

COMMON_PASSWORDS = {"password", "password1", "password123", "qwerty123", "1234567890", "iloveyou", "aiwazz123"}
INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
API_KEY_PREFIX = "aiw_live_"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def password_problem(password: str, email: str, min_length: int) -> str | None:
    """Server-side password policy (the UI shows a strength meter on top of this)."""
    if len(password) < min_length:
        return f"Use at least {min_length} characters"
    if len(password) > 128:
        return "Use at most 128 characters"
    low = password.lower()
    if low in COMMON_PASSWORDS or low == email.lower() or low == email.split("@")[0].lower():
        return "This password is too easy to guess"
    if len(set(password)) < 4:
        return "This password is too easy to guess"
    return None


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def new_invite_code() -> str:
    raw = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_invite(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


def new_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(30)
