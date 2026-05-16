import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    tenant_id: str,
    role: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, tenant_id: str) -> Tuple[str, str, datetime]:
    jti = secrets.token_hex(32)
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expire


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def verify_token(token: str, expected_type: str = "access") -> Optional[Dict[str, Any]]:
    try:
        payload = decode_token(token)
        if payload.get("type") != expected_type:
            return None
        return payload
    except JWTError:
        return None


def get_fernet() -> Fernet:
    key = hashlib.sha256(settings.aes_encryption_key.encode()).digest()
    import base64
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(value: str) -> str:
    return get_fernet().encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    return get_fernet().decrypt(encrypted.encode()).decode()


def hash_fingerprint(fingerprint_data: Dict[str, Any]) -> str:
    canonical = "|".join(f"{k}={fingerprint_data.get(k, '')}" for k in sorted(fingerprint_data))
    return hashlib.sha256(canonical.encode()).hexdigest()


def generate_api_key() -> Tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    prefix = raw[:8]
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return f"ss_{prefix}_{raw[8:]}", hashed
