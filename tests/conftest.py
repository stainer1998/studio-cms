import re

import pyotp
import pytest
from sqlalchemy import text

from app import create_app
from app.auth.models import User
from app.config import TestConfig
from app.extensions import db, limiter

PASSWORD = "contraseña-de-prueba-larga"


@pytest.fixture(scope="session")
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        db.session.commit()
        db.create_all()
    return app


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.remove()
        tables = ", ".join(t.name for t in db.metadata.sorted_tables)
        db.session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()
    limiter.reset()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    """Administrador con TOTP conocido. Devuelve (secreto TOTP, códigos de recuperación)."""
    with app.app_context():
        user = User(email="admin@vfdigital.cl")
        user.set_password(PASSWORD)
        secret = user.new_totp_secret()
        codes = user.new_recovery_codes()
        db.session.add(user)
        db.session.commit()
    return secret, codes


def csrf(client, url):
    html = client.get(url, follow_redirects=True).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def post(client, url, data, form_url=None, **kwargs):
    """POST con el token CSRF tomado de la página que contiene el formulario."""
    return client.post(url, data={**data, "csrf_token": csrf(client, form_url or url)}, **kwargs)


def login(client, secret, password=PASSWORD):
    post(client, "/login", {"email": "admin@vfdigital.cl", "password": password})
    return post(client, "/login/2fa", {"code": pyotp.TOTP(secret).now()})


@pytest.fixture
def auth_client(client, admin):
    login(client, admin[0])
    return client


def create_site(client, name, key, domain=None):
    return post(
        client,
        "/sitios/nuevo",
        {"name": name, "key": key, "domain": domain or f"{key}.cl"},
    )
