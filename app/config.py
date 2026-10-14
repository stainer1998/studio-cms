import os
from datetime import timedelta
from pathlib import Path


def _flag(name, default):
    return os.environ.get(name, default).lower() in {"1", "true", "yes"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = REDIS_URL

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", "true")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Intentos fallidos de inicio de sesión permitidos por correo antes del bloqueo.
    LOGIN_LIMIT = "5 per 15 minutes"
    AUDIT_PAGE_SIZE = 50

    # Medios (H3). En Docker, MEDIA_ROOT es un volumen compartido entre web y worker.
    MEDIA_ROOT = os.environ.get("MEDIA_ROOT") or str(Path(__file__).parents[1] / "storage/media")
    MEDIA_MAX_BYTES = int(os.environ.get("MEDIA_MAX_MB", "10")) * 1024 * 1024
    # Tope de la petición completa (se pueden subir varios archivos a la vez).
    MAX_CONTENT_LENGTH = 10 * MEDIA_MAX_BYTES
    RQ_ASYNC = True


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "pruebas"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://studio:studio@localhost:5432/studio_test"
    )
    RATELIMIT_STORAGE_URI = "memory://"
    SESSION_COOKIE_SECURE = False
    RQ_ASYNC = False  # los trabajos corren en línea para poder comprobar su resultado
