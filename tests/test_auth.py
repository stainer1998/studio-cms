from sqlalchemy import select

from app.auth.models import User
from app.core.models import AuditLog
from app.extensions import db
from tests.conftest import PASSWORD, login, post


def actions(app):
    with app.app_context():
        q = select(AuditLog.action).order_by(AuditLog.id).execution_options(all_sites=True)
        return db.session.scalars(q).all()


def test_sin_sesion_redirige_al_inicio_de_sesion(client):
    for url in ["/", "/sitios/", "/auditoria"]:
        r = client.get(url)
        assert r.status_code == 302 and r.location.endswith("/login")


def test_contrasena_correcta_sin_totp_no_da_acceso(client, admin):
    r = post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    assert r.location.endswith("/login/2fa")
    assert client.get("/").location.endswith("/login")


def test_totp_valido_da_acceso_y_queda_en_auditoria(app, client, admin):
    r = login(client, admin[0])
    assert r.status_code == 302
    assert client.get("/sitios/").status_code == 200
    assert actions(app) == ["iniciar_sesion"]


def test_totp_invalido_es_rechazado(client, admin):
    post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    r = post(client, "/login/2fa", {"code": "000000"})
    assert r.status_code == 401
    assert client.get("/").location.endswith("/login")


def test_contrasena_incorrecta(client, admin):
    r = post(client, "/login", {"email": "admin@vfdigital.cl", "password": "otra"})
    assert r.status_code == 401
    assert "Correo o contraseña incorrectos" in r.get_data(as_text=True)


def test_codigo_de_recuperacion_sirve_una_sola_vez(app, client, admin):
    code = admin[1][0]
    post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    assert post(client, "/login/2fa", {"code": code}).status_code == 302
    with app.app_context():
        assert len(db.session.scalar(select(User)).recovery_codes) == 9

    post(client, "/logout", {}, form_url="/")
    post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    assert post(client, "/login/2fa", {"code": code}).status_code == 401


def test_bloqueo_tras_intentos_fallidos(app, client, admin):
    for _ in range(5):
        r = post(client, "/login", {"email": "admin@vfdigital.cl", "password": "mala"})
        assert r.status_code == 401
    # Bloqueado incluso con la contraseña correcta.
    r = post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    assert r.status_code == 429
    assert "Demasiados intentos" in r.get_data(as_text=True)
    assert actions(app)[-1] == "login_bloqueado"


def test_codigos_totp_fallidos_cuentan_para_el_bloqueo(client, admin):
    post(client, "/login", {"email": "admin@vfdigital.cl", "password": PASSWORD})
    for _ in range(5):
        assert post(client, "/login/2fa", {"code": "000000"}).status_code == 401
    assert post(client, "/login/2fa", {"code": "000000"}).status_code == 429


def test_formularios_sin_csrf_son_rechazados(client, admin):
    r = client.post("/login", data={"email": "admin@vfdigital.cl", "password": PASSWORD})
    assert r.status_code == 400


def test_cabeceras_de_seguridad(client):
    r = client.get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
