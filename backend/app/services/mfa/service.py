import base64
import io
from typing import Optional, Tuple

import pyotp

from app.core.config import get_settings
from app.core.security import decrypt_value, encrypt_value

settings = get_settings()

ADMIN_ROLES = {"super_admin", "admin", "analyst"}


class MFAService:
    @staticmethod
    def generate_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(secret: str, email: str) -> str:
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=settings.app_name)

    @staticmethod
    def verify_code(secret: str, code: str) -> bool:
        if not secret or not code:
            return False
        try:
            plain = decrypt_value(secret) if secret.startswith("gAAAA") else secret
        except Exception:
            plain = secret
        totp = pyotp.TOTP(plain)
        return totp.verify(code, valid_window=1)

    @staticmethod
    def encrypt_secret(secret: str) -> str:
        return encrypt_value(secret)

    @staticmethod
    def qr_code_base64(uri: str) -> str:
        import qrcode
        img = qrcode.make(uri)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    @staticmethod
    def requires_mfa(role: str) -> bool:
        return role in ADMIN_ROLES
