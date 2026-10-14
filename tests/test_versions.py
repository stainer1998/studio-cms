from sqlalchemy import select

from app.content.models import Entry, EntryVersion
from app.extensions import db
from tests.conftest import post, product_type, save_entry


def versions(app):
    with app.app_context():
        q = select(EntryVersion).order_by(EntryVersion.id).execution_options(all_sites=True)
        return db.session.scalars(q).all()


def test_cada_guardado_crea_una_version_y_se_compara(app, site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Hallulla", precio="300")
    save_entry(
        site_client, "/contenido/entradas/1", nombre="Hallulla", precio="350", status="listo"
    )
    v = versions(app)
    assert [x.data["precio"] for x in v] == [300, 350]

    html = site_client.get("/contenido/entradas/1/versiones").get_data(as_text=True)
    assert "Actual" in html and "Restaurar" in html
    r = site_client.get(
        f"/contenido/entradas/1/versiones?a={v[0].id}&b={v[1].id}", headers={"HX-Request": "true"}
    )
    html = r.get_data(as_text=True)
    assert "<html" not in html and "Precio" in html and "300" in html and "350" in html
    assert "Listo para exportar" in html and "Nombre" not in html  # solo lo que cambió


def test_restaurar_version(app, site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Hallulla", precio="300")
    save_entry(site_client, "/contenido/entradas/1", nombre="Hallulla grande", precio="500")
    first = versions(app)[0].id
    r = post(
        site_client,
        f"/contenido/entradas/1/versiones/{first}/restaurar",
        {},
        form_url="/contenido/entradas/1/versiones",
        headers={"HX-Request": "true"},
    )
    assert r.headers["HX-Redirect"] == "/contenido/entradas/1"
    with app.app_context():
        e = db.session.scalar(select(Entry).execution_options(all_sites=True))
        assert e.data["precio"] == 300 and e.slug == "hallulla"
    assert len(versions(app)) == 3  # restaurar también deja versión


def test_entradas_y_modelos_quedan_en_auditoria(site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Hallulla", precio="300")
    html = site_client.get("/auditoria").get_data(as_text=True)
    assert "Modelo «Producto»" in html and "Entrada «Hallulla»" in html
