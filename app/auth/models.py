import secrets
from datetime import datetime

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask_login import UserMixin
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

ph = PasswordHasher()
# Hash contra el que se verifica si el correo no existe: así el tiempo no lo delata.
DUMMY_HASH = ph.hash("no-existe")


def verify_hash(hash_, value):
    try:
        return ph.verify(hash_, value)
    except (VerificationError, InvalidHashError):
        return False


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    totp_secret: Mapped[str] = mapped_column(String(64))
    recovery_codes: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]

    def set_password(self, password):
        self.password_hash = ph.hash(password)

    def check_password(self, password):
        return verify_hash(self.password_hash, password)

    def new_totp_secret(self):
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret

    def totp_uri(self):
        return pyotp.TOTP(self.totp_secret).provisioning_uri(self.email, issuer_name="Studio CMS")

    def check_totp(self, code):
        return pyotp.TOTP(self.totp_secret).verify(code, valid_window=1)

    def new_recovery_codes(self, n=10):
        """Genera códigos nuevos (invalida los anteriores) y los devuelve en claro una vez."""
        codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(n)]
        self.recovery_codes = [ph.hash(c) for c in codes]
        return codes

    def use_recovery_code(self, code):
        """Consume el código si es válido: cada uno sirve una sola vez."""
        code = code.strip().lower()
        for h in self.recovery_codes:
            if verify_hash(h, code):
                self.recovery_codes = [x for x in self.recovery_codes if x != h]
                return True
        return False
