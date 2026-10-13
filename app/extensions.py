from datetime import datetime

from flask import request, session
from flask_limiter import Limiter
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, registry


class Base(DeclarativeBase):
    registry = registry(
        # Fechas siempre con zona horaria (timestamptz), guardadas en UTC.
        type_annotation_map={datetime: DateTime(timezone=True)},
        # Nombres de restricciones estables para que Alembic genere migraciones reproducibles.
        metadata=MetaData(
            naming_convention={
                "ix": "ix_%(column_0_label)s",
                "uq": "uq_%(table_name)s_%(column_0_name)s",
                "ck": "ck_%(table_name)s_%(constraint_name)s",
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
                "pk": "pk_%(table_name)s",
            }
        ),
    )


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def login_key():
    """Clave del límite de intentos: el correo que se intenta usar, no la IP."""
    email = request.form.get("email") or session.get("pending_email") or ""
    return "login:" + email.strip().lower()


limiter = Limiter(key_func=login_key)
