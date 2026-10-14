import io
import re

import pyotp
import pytest
from PIL import Image
from sqlalchemy import text

from app import create_app
from app.auth.models import User
from app.config import TestConfig
from app.extensions import db, limiter

PASSWORD = "contraseña-de-prueba-larga"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    app = create_app(TestConfig)
    app.config["MEDIA_ROOT"] = str(tmp_path_factory.mktemp("medios"))
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


@pytest.fixture
def site_client(auth_client):
    """Cliente autenticado con un sitio activo."""
    create_site(auth_client, "Panadería Los Aromos", "los-aromos")
    return auth_client


def create_type(client, name, key):
    r = post(client, "/modelos/nuevo", {"name": name, "key": key})
    assert r.status_code == 302, r.get_data(as_text=True)
    return int(r.location.rstrip("/").split("/")[-1].split("?")[0])


def add_field(client, type_id, key, label, ftype="text", **opts):
    data = {"label": label, "key": key, "type": ftype, **opts}
    return post(client, f"/modelos/{type_id}/campos", data, form_url=f"/modelos/{type_id}")


def product_type(client):
    """Modelos Categoría y Producto como en el prototipo. Devuelve (id categoría, id producto)."""
    cat = create_type(client, "Categoría", "categoria")
    add_field(client, cat, "nombre", "Nombre", required="on")
    add_field(client, cat, "slug", "Slug", "slug", slug_source="nombre", required="on")
    prod = create_type(client, "Producto", "producto")
    add_field(client, prod, "nombre", "Nombre", required="on", maximum="80")
    add_field(client, prod, "slug", "Slug", "slug", slug_source="nombre", required="on")
    add_field(client, prod, "descripcion", "Descripción", "rich")
    add_field(
        client,
        prod,
        "precio",
        "Precio",
        "number",
        required="on",
        minimum="0",
        help="Precio en pesos chilenos, sin puntos.",
    )
    add_field(client, prod, "destacado", "Destacado", "bool")
    add_field(client, prod, "categoria", "Categoría", "relation", ref=str(cat))
    return cat, prod


def save_entry(client, url, form_url=None, **data):
    data.setdefault("status", "borrador")
    return post(client, url, data, form_url=form_url or url)


def image_bytes(width=2000, height=1000, fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "#C9A27E").save(buf, fmt)
    return buf.getvalue()


def upload(client, *files):
    """Sube (nombre, bytes) a Medios. Devuelve la respuesta (redirige a la ficha del último)."""
    data = {"archivos": [(io.BytesIO(content), name) for name, content in files]}
    return post(client, "/medios/subir", data, form_url="/medios/")


def media_id(response):
    return int(response.location.rstrip("/").split("/")[-1])
