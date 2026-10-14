from sqlalchemy import select

from app.extensions import db
from app.media.models import Media, MediaUsage
from tests.conftest import (
    add_field,
    create_site,
    image_bytes,
    media_id,
    post,
    product_type,
    save_entry,
    upload,
)


def usages(app):
    with app.app_context():
        q = select(MediaUsage.media_id, MediaUsage.entry_id).order_by(MediaUsage.media_id)
        return [tuple(r) for r in db.session.execute(q.execution_options(all_sites=True))]


def media_count(app):
    with app.app_context():
        return len(db.session.scalars(select(Media).execution_options(all_sites=True)).all())


def product_with_photo(client):
    _, prod = product_type(client)
    add_field(client, prod, "foto", "Foto", "image", required="on")
    return prod


def test_campo_imagen_requerido_y_selector(site_client):
    prod = product_with_photo(site_client)
    html = site_client.get(f"/contenido/{prod}/nueva").get_data(as_text=True)
    assert "data-image-field" in html and "media.js" in html
    r = save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1")
    assert r.status_code == 422
    assert "Este campo es obligatorio." in r.get_data(as_text=True)

    mid = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    picker = site_client.get("/medios/selector").get_data(as_text=True)
    assert f'data-pick-id="{mid}"' in picker and f'data-src="/medios/{mid}/mediana"' in picker
    r = save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1", foto=str(mid))
    assert r.status_code == 302
    html = site_client.get(r.location).get_data(as_text=True)
    assert f'src="/medios/{mid}/miniatura"' in html


def test_campo_imagen_rechaza_documentos_y_medios_de_otro_sitio(site_client):
    prod = product_with_photo(site_client)
    pdf = media_id(upload(site_client, ("carta.pdf", b"%PDF-1.4")))
    r = save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1", foto=str(pdf))
    assert "Elige una imagen de la biblioteca de Medios." in r.get_data(as_text=True)

    img = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    create_site(site_client, "Clínica", "clinica")
    _, other = product_type(site_client)
    add_field(site_client, other, "foto", "Foto", "image")
    r = save_entry(site_client, f"/contenido/{other}/nueva", nombre="X", precio="1", foto=str(img))
    assert "Elige una imagen de la biblioteca de Medios." in r.get_data(as_text=True)


def test_ficha_lista_las_entradas_e_impide_eliminar_en_uso(app, site_client):
    prod = product_with_photo(site_client)
    foto = media_id(upload(site_client, ("masa-madre.png", image_bytes(400, 200))))
    en_texto = media_id(upload(site_client, ("miga.png", image_bytes(400, 200))))
    libre = media_id(upload(site_client, ("libre.png", image_bytes(400, 200))))
    save_entry(
        site_client,
        f"/contenido/{prod}/nueva",
        nombre="Pan de masa madre",
        precio="3500",
        foto=str(foto),
        descripcion=f'<p>Miga abierta</p><img src="/medios/{en_texto}/mediana" alt="Miga">',
    )
    assert usages(app) == [(foto, 1), (en_texto, 1)]

    html = site_client.get(f"/medios/{en_texto}").get_data(as_text=True)
    assert "Entrada «Pan de masa madre»" in html and "/contenido/entradas/1" in html
    assert "No se puede eliminar mientras esté en uso." in html
    sin_usar = site_client.get(
        "/medios/?tipo=sin-usar", headers={"HX-Request": "true", "HX-Target": "medios"}
    ).get_data(as_text=True)
    assert "libre.png" in sin_usar and "masa-madre.png" not in sin_usar

    r = post(site_client, f"/medios/{foto}/eliminar", {}, form_url=f"/medios/{foto}")
    assert "está en uso y no se puede eliminar" in site_client.get(r.location).get_data(
        as_text=True
    )
    assert media_count(app) == 3

    # Al quitar la imagen del texto, el medio deja de estar en uso y se puede eliminar.
    save_entry(
        site_client,
        "/contenido/entradas/1",
        nombre="Pan de masa madre",
        precio="3500",
        foto=str(foto),
        descripcion="<p>Miga abierta</p>",
    )
    assert usages(app) == [(foto, 1)]
    post(site_client, f"/medios/{en_texto}/eliminar", {}, form_url=f"/medios/{en_texto}")
    post(site_client, f"/medios/{libre}/eliminar", {}, form_url=f"/medios/{libre}")
    assert media_count(app) == 1


def test_restaurar_version_recalcula_los_usos(app, site_client):
    prod = product_with_photo(site_client)
    a = media_id(upload(site_client, ("a.png", image_bytes(400, 200))))
    b = media_id(upload(site_client, ("b.png", image_bytes(400, 200))))
    save_entry(site_client, f"/contenido/{prod}/nueva", nombre="Pan", precio="1", foto=str(a))
    save_entry(site_client, "/contenido/entradas/1", nombre="Pan", precio="1", foto=str(b))
    assert usages(app) == [(b, 1)]
    post(
        site_client,
        "/contenido/entradas/1/versiones/1/restaurar",
        {},
        form_url="/contenido/entradas/1/versiones",
    )
    assert usages(app) == [(a, 1)]
