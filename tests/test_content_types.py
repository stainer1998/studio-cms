from flask import g
from sqlalchemy import select

from app.content.models import ContentType, Entry
from app.extensions import db
from tests.conftest import add_field, create_site, create_type, post, product_type, save_entry


def get_type(app, type_id):
    with app.app_context():
        q = select(ContentType).where(ContentType.id == type_id)
        return db.session.scalar(q.execution_options(all_sites=True))


def test_crear_modelo_y_clave_unica_por_sitio(app, site_client):
    create_type(site_client, "Producto", "producto")
    r = post(site_client, "/modelos/nuevo", {"name": "Otro", "key": "producto"})
    assert "Ya existe un modelo con ese nombre interno" in r.get_data(as_text=True)
    r = post(site_client, "/modelos/nuevo", {"name": "Otro", "key": "Mal Nombre"})
    assert "Usa minúsculas" in r.get_data(as_text=True)

    create_site(site_client, "Clínica", "clinica")  # queda activo
    create_type(site_client, "Producto", "producto")  # misma clave, otro sitio: permitido


def test_esquema_generado_desde_los_campos(app, site_client):
    cat, prod = product_type(site_client)
    schema = get_type(app, prod).schema
    assert list(schema["properties"]) == [
        "nombre",
        "slug",
        "descripcion",
        "precio",
        "destacado",
        "categoria",
    ]
    assert schema["required"] == ["nombre", "slug", "precio"]
    props = schema["properties"]
    assert props["nombre"] == {
        "title": "Nombre",
        "x-type": "text",
        "type": "string",
        "maxLength": 80,
    }
    assert props["slug"]["pattern"] == "^[a-z0-9]+(-[a-z0-9]+)*$"
    assert props["descripcion"]["format"] == "html"
    assert props["precio"] == {
        "title": "Precio",
        "x-type": "number",
        "type": "number",
        "minimum": 0,
        "description": "Precio en pesos chilenos, sin puntos.",
    }
    assert props["destacado"] == {
        "title": "Destacado",
        "x-type": "bool",
        "type": "boolean",
        "default": False,
    }
    assert props["categoria"] == {
        "title": "Categoría",
        "x-type": "relation",
        "type": "integer",
        "x-ref": cat,
    }
    assert get_type(app, prod).slug_source == "nombre"
    # El esquema se ve en la pantalla del modelo.
    html = site_client.get(f"/modelos/{prod}").get_data(as_text=True)
    assert "Esquema JSON generado" in html and "&#34;x-ref&#34;" in html


def test_validaciones_del_campo(site_client):
    t = create_type(site_client, "Producto", "producto")
    add_field(site_client, t, "nombre", "Nombre")
    r = add_field(site_client, t, "nombre", "Repetido")
    assert r.status_code == 422 and "Ya existe un campo con ese nombre interno" in r.get_data(
        as_text=True
    )
    r = add_field(site_client, t, "precio", "Precio", "number", minimum="10", maximum="5")
    assert "El máximo debe ser mayor o igual al mínimo" in r.get_data(as_text=True)
    r = add_field(site_client, t, "slug", "Slug", "slug")
    assert "Elige el campo de texto" in r.get_data(as_text=True)
    add_field(site_client, t, "slug", "Slug", "slug", slug_source="nombre")
    r = add_field(site_client, t, "slug2", "Otro slug", "slug", slug_source="nombre")
    assert "El modelo ya tiene un campo slug" in r.get_data(as_text=True)


def test_relacion_solo_hacia_modelos_del_mismo_sitio(app, site_client):
    t = create_type(site_client, "Producto", "producto")
    create_site(site_client, "Clínica", "clinica")
    otro = create_type(site_client, "Servicio", "servicio")
    post(site_client, "/sitios/activo", {"site_id": 1}, form_url="/")
    r = add_field(site_client, t, "servicio", "Servicio", "relation", ref=str(otro))
    assert r.status_code == 422 and "Elige el modelo relacionado" in r.get_data(as_text=True)


def test_editar_y_reordenar_campos(app, site_client):
    t = create_type(site_client, "Producto", "producto")
    add_field(site_client, t, "nombre", "Nombre")
    add_field(site_client, t, "precio", "Precio", "number")
    post(
        site_client,
        f"/modelos/{t}/campos/precio",
        {"label": "Precio CLP", "type": "number", "required": "on", "maximum": "99000"},
        form_url=f"/modelos/{t}",
    )
    schema = get_type(app, t).schema
    assert schema["properties"]["precio"]["title"] == "Precio CLP"
    assert schema["properties"]["precio"]["maximum"] == 99000
    assert schema["required"] == ["precio"]

    r = post(
        site_client,
        f"/modelos/{t}/campos/precio/mover",
        {"dir": "arriba"},
        form_url=f"/modelos/{t}",
        headers={"HX-Request": "true"},
    )
    assert "<html" not in r.get_data(as_text=True)  # fragmento HTMX
    assert list(get_type(app, t).schema["properties"]) == ["precio", "nombre"]


def test_eliminar_campo_con_datos_avisa_y_borra(app, site_client):
    _, prod = product_type(site_client)
    for nombre in ("Marraqueta", "Hallulla"):
        save_entry(
            site_client, f"/contenido/{prod}/nueva", nombre=nombre, precio="1000", destacado="on"
        )
    r = site_client.get(f"/modelos/{prod}/campos/precio/eliminar", headers={"HX-Request": "true"})
    assert "2 entradas tienen datos en este campo" in r.get_data(as_text=True)

    post(site_client, f"/modelos/{prod}/campos/precio/eliminar", {}, form_url=f"/modelos/{prod}")
    assert "precio" not in get_type(app, prod).schema["properties"]
    with app.app_context():
        datas = db.session.scalars(select(Entry.data).execution_options(all_sites=True)).all()
    assert all("precio" not in d for d in datas)

    r = site_client.get(f"/modelos/{prod}/campos/destacado/eliminar")
    assert "2 entradas tienen datos" in r.get_data(as_text=True)


def test_el_tipo_no_cambia_si_hay_datos(app, site_client):
    _, prod = product_type(site_client)
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1000")
    post(
        site_client,
        f"/modelos/{prod}/campos/precio",
        {"label": "Precio", "type": "text"},
        form_url=f"/modelos/{prod}",
    )
    assert get_type(app, prod).schema["properties"]["precio"]["x-type"] == "number"


def test_modelo_de_otro_sitio_da_404(app, site_client):
    t = create_type(site_client, "Producto", "producto")
    create_site(site_client, "Clínica", "clinica")
    assert site_client.get(f"/modelos/{t}").status_code == 404
    r = post(
        site_client,
        f"/modelos/{t}/campos",
        {"label": "X", "key": "x", "type": "text"},
        form_url="/",
    )
    assert r.status_code == 404
    with app.app_context():
        g.site_id = 2
        assert db.session.scalars(select(ContentType)).all() == []
