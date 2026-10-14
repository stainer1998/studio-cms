from flask import g
from sqlalchemy import select

from app.content.models import Entry
from app.extensions import db
from tests.conftest import add_field, create_site, post, product_type, save_entry


def entries(app):
    with app.app_context():
        q = select(Entry).order_by(Entry.id).execution_options(all_sites=True)
        return db.session.scalars(q).all()


def test_formulario_generado_desde_el_modelo(site_client):
    _, prod = product_type(site_client)
    html = site_client.get(f"/contenido/{prod}/nueva").get_data(as_text=True)
    for fragment in [
        'name="nombre"',
        'name="slug"',
        "data-rich",
        'type="number"',
        'type="checkbox" id="f-destacado"',
        '<select id="f-categoria"',
        "Precio en pesos chilenos",
        "dist/tiptap.js",
    ]:
        assert fragment in html, fragment
    # Un cambio en el modelo se refleja de inmediato en el formulario.
    add_field(site_client, prod, "fecha", "Elaborado el", "date")
    assert 'type="date"' in site_client.get(f"/contenido/{prod}/nueva").get_data(as_text=True)


def test_crear_entrada_tipada_y_slug_generado(app, site_client):
    cat, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{cat}/nueva", nombre="Panes")
    r = save_entry(
        site_client,
        f"/contenido/{prod}/nueva",
        nombre="Pan de Masa Madre",
        precio="3500",
        destacado="on",
        categoria="1",
        descripcion="<p>Fermentación <strong>lenta</strong></p>",
        status="listo",
    )
    assert r.status_code == 302
    e = entries(app)[-1]
    assert e.slug == "pan-de-masa-madre" and e.status == "listo"
    assert e.data == {
        "nombre": "Pan de Masa Madre",
        "slug": "pan-de-masa-madre",
        "precio": 3500,
        "destacado": True,
        "categoria": 1,
        "descripcion": "<p>Fermentación <strong>lenta</strong></p>",
    }


def test_errores_junto_al_campo_sin_perder_lo_escrito(app, site_client):
    _, prod = product_type(site_client)
    r = save_entry(
        site_client,
        f"/contenido/{prod}/nueva",
        nombre="x" * 81,
        precio="-5",
        descripcion="<p>Texto escrito</p>",
    )
    html = r.get_data(as_text=True)
    assert r.status_code == 422
    assert "Debe tener como máximo 80 caracteres." in html
    assert "Debe ser mayor o igual a 0." in html
    assert 'id="f-precio-error"' in html and 'aria-invalid="true"' in html
    assert "x" * 81 in html and "Texto escrito" in html  # lo escrito se conserva
    r = save_entry(site_client, f"/contenido/{prod}/nueva", precio="abc")
    html = r.get_data(as_text=True)
    assert "Este campo es obligatorio." in html and "Escribe un número." in html
    assert entries(app) == []


def test_slug_unico_dentro_del_modelo(app, site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Hallulla", precio="300")
    r = save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Hallulla", precio="400")
    assert "Ya existe una entrada con ese slug" in r.get_data(as_text=True)
    r = save_entry(
        site_client, f"/contenido/{prod}/nueva", nombre="Otra", slug="Con Espacios", precio="1"
    )
    assert "Usa solo minúsculas, números y guiones." in r.get_data(as_text=True)


def test_relacion_solo_acepta_entradas_del_modelo(app, site_client):
    cat, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1")
    # La entrada 1 es un producto, no una categoría.
    r = save_entry(
        site_client, f"/contenido/{prod}/nueva", nombre="Otro", precio="1", categoria="1"
    )
    assert "Elige una entrada del modelo relacionado." in r.get_data(as_text=True)


def test_html_enriquecido_se_sanitiza(app, site_client):
    _, prod = product_type(site_client)
    save_entry(
        site_client,
        f"/contenido/{prod}/nueva",
        nombre="Pan",
        precio="1",
        descripcion='<p onclick="x()">Hola<script>alert(1)</script> '
        '<a href="javascript:alert(1)">a</a> <a href="https://vf.cl">b</a>'
        '<img src="/x.webp" alt="pan" onerror="y()"></p><iframe src="x"></iframe>',
    )
    html = entries(app)[-1].data["descripcion"]
    assert "script" not in html and "onclick" not in html and "onerror" not in html
    assert "javascript" not in html and "iframe" not in html
    assert '<a href="https://vf.cl" rel="noopener noreferrer">b</a>' in html
    assert '<img src="/x.webp" alt="pan">' in html
    # Un editor vacío no guarda nada.
    save_entry(
        site_client, f"/contenido/{prod}/nueva", nombre="Vacío", precio="1", descripcion="<p></p>"
    )
    assert "descripcion" not in entries(app)[-1].data


def test_lista_busqueda_y_filtro(site_client):
    _, prod = product_type(site_client)
    save_entry(
        site_client, f"/contenido/{prod}/nueva", nombre="Marraqueta", precio="1", status="listo"
    )
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Empanada de pino", precio="1")
    url = f"/contenido/{prod}/"
    html = site_client.get(url).get_data(as_text=True)
    assert "Producto · 2" in html and "Marraqueta" in html and "Empanada de pino" in html
    r = site_client.get(url + "?q=PINO", headers={"HX-Request": "true"})
    html = r.get_data(as_text=True)
    assert "<html" not in html and "Empanada de pino" in html and "Marraqueta" not in html
    html = site_client.get(url + "?estado=listo").get_data(as_text=True)
    assert "Marraqueta" in html and "Empanada de pino" not in html
    html = site_client.get(url + "?q=100%25").get_data(as_text=True)
    assert "No hay entradas que coincidan" in html


def test_entrada_de_otro_sitio_da_404(app, site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1")
    create_site(site_client, "Clínica", "clinica")
    assert site_client.get("/contenido/entradas/1").status_code == 404
    assert site_client.get("/contenido/entradas/1/versiones").status_code == 404
    assert site_client.get(f"/contenido/{prod}/").status_code == 404
    r = post(site_client, "/contenido/entradas/1/versiones/1/restaurar", {}, form_url="/")
    assert r.status_code == 404
    with app.app_context():
        g.site_id = 2
        assert db.session.scalars(select(Entry)).all() == []
