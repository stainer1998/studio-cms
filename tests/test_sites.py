from sqlalchemy import select

from app.extensions import db
from app.sites.models import Site
from tests.conftest import create_site, post


def sites(app):
    with app.app_context():
        return {s.key: s for s in db.session.scalars(select(Site)).all()}


def selector(client):
    html = client.get("/").get_data(as_text=True)
    return html[html.index('id="site_id"') : html.index("</select>")]


def test_sin_sitios_pide_crear_uno(auth_client):
    assert auth_client.get("/").location.endswith("/sitios/nuevo")


def test_crear_sitio_lo_deja_activo(app, auth_client):
    r = create_site(auth_client, "Panadería Los Aromos", "los-aromos", "https://LosAromos.cl/")
    assert r.location.endswith("/")
    site = sites(app)["los-aromos"]
    assert site.domain == "losaromos.cl"
    assert "Panadería Los Aromos" in auth_client.get("/").get_data(as_text=True)


def test_clave_duplicada_e_invalida(auth_client):
    create_site(auth_client, "Uno", "uno")
    r = create_site(auth_client, "Otro", "uno")
    assert "Ya existe un sitio con esa clave" in r.get_data(as_text=True)
    r = create_site(auth_client, "Otro", "Con Espacios")
    assert "Usa minúsculas, números y guiones" in r.get_data(as_text=True)
    r = create_site(auth_client, "Otro", "otro", "no es dominio")
    assert "Escribe un dominio válido" in r.get_data(as_text=True)


def test_editar_sitio(app, auth_client):
    create_site(auth_client, "Uno", "uno")
    site_id = sites(app)["uno"].id
    url = f"/sitios/{site_id}/editar"
    post(auth_client, url, {"name": "Uno editado", "key": "uno", "domain": "uno.cl"})
    assert sites(app)["uno"].name == "Uno editado"


def test_archivar_y_restaurar(app, auth_client):
    create_site(auth_client, "Panadería", "panaderia")
    create_site(auth_client, "Clínica", "clinica")
    clinica = sites(app)["clinica"].id

    post(auth_client, f"/sitios/{clinica}/archivar", {}, form_url="/sitios/")
    assert sites(app)["clinica"].archived_at is not None
    assert "Clínica" not in selector(auth_client)
    assert "Clínica" in auth_client.get("/sitios/").get_data(as_text=True)  # en Archivados

    post(auth_client, f"/sitios/{clinica}/restaurar", {}, form_url="/sitios/")
    assert sites(app)["clinica"].archived_at is None
    assert "Clínica" in selector(auth_client)


def test_cambiar_sitio_activo(app, auth_client):
    create_site(auth_client, "Panadería", "panaderia")
    create_site(auth_client, "Clínica", "clinica")
    panaderia = sites(app)["panaderia"].id

    r = post(auth_client, "/sitios/activo", {"site_id": panaderia}, form_url="/")
    assert r.status_code == 302
    assert f'<option value="{panaderia}" selected' in selector(auth_client)

    r = post(
        auth_client,
        "/sitios/activo",
        {"site_id": panaderia},
        form_url="/",
        headers={"HX-Request": "true"},
    )
    assert r.headers["HX-Redirect"] == "/"


def test_no_se_puede_activar_un_sitio_archivado(app, auth_client):
    create_site(auth_client, "Panadería", "panaderia")
    create_site(auth_client, "Clínica", "clinica")
    clinica = sites(app)["clinica"].id
    post(auth_client, f"/sitios/{clinica}/archivar", {}, form_url="/sitios/")
    r = post(auth_client, "/sitios/activo", {"site_id": clinica}, form_url="/")
    assert r.status_code == 400
