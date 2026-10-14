import io

from PIL import Image
from sqlalchemy import select

from app.core.models import AuditLog
from app.extensions import db
from app.media import files
from app.media.models import Media
from app.media.tasks import generate_variants
from tests.conftest import create_site, image_bytes, media_id, post, upload


def all_media(app):
    with app.app_context():
        q = select(Media).order_by(Media.id).execution_options(all_sites=True)
        return db.session.scalars(q).all()


def test_rechaza_contenido_distinto_a_la_extension(app, site_client):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    r = upload(
        site_client,
        ("foto.jpg", b"esto es texto, no una imagen"),
        ("logo.svg", svg),
        ("carta.pdf", b"PDX-no-es-un-pdf"),
        ("trunca.png", image_bytes()[:200]),
    )
    html = site_client.get(r.location).get_data(as_text=True)
    for name in ["foto.jpg", "logo.svg", "carta.pdf", "trunca.png"]:
        assert f"«{name}» no es una imagen JPEG, PNG, WebP o GIF ni un PDF válido" in html
    assert all_media(app) == []


def test_acepta_formatos_validos_por_su_contenido(app, site_client):
    r = upload(
        site_client,
        ("a.jpg", image_bytes(400, 300, "JPEG")),
        ("b.png", image_bytes(400, 300, "PNG")),
        ("c.webp", image_bytes(400, 300, "WEBP")),
        ("d.gif", image_bytes(400, 300, "GIF")),
        # La extensión no importa: el tipo se toma del contenido.
        ("carta-precios.txt", b"%PDF-1.7\n%contenido"),
    )
    assert r.status_code == 302
    mimes = [m.mime for m in all_media(app)]
    assert mimes == ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"]
    pdf = all_media(app)[-1]
    assert pdf.variants == {} and pdf.width is None
    r = site_client.get(f"/medios/{pdf.id}/archivo")
    assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF-")


def test_tamano_maximo(app, site_client, monkeypatch):
    monkeypatch.setitem(app.config, "MEDIA_MAX_BYTES", 1024 * 1024)
    r = upload(site_client, ("enorme.png", image_bytes()[:10] + b"0" * (1024 * 1024 + 1)))
    assert "«enorme.png» supera el tamaño máximo de 1 MB" in site_client.get(r.location).get_data(
        as_text=True
    )
    assert all_media(app) == []


def test_variantes_en_segundo_plano_y_utilizable_mientras_tanto(app, site_client, monkeypatch):
    queued = []
    monkeypatch.setattr("app.media.routes.enqueue", lambda func, *args: queued.append(args))
    mid = media_id(upload(site_client, ("masa-madre.png", image_bytes(2000, 1000))))

    # La petición solo encola el trabajo; el archivo ya se puede usar con el original.
    assert queued == [(mid,)]
    assert all_media(app)[0].variants is None
    r = site_client.get(f"/medios/{mid}/mediana")
    assert r.status_code == 200 and r.mimetype == "image/png"
    html = site_client.get(f"/medios/{mid}").get_data(as_text=True)
    assert "Generando variantes" in html and 'hx-trigger="every 2s"' in html

    with app.app_context():
        generate_variants(mid)  # lo que hace el trabajador RQ
    media = all_media(app)[0]
    assert media.variants == {
        "miniatura": {"width": 320, "height": 160},
        "mediana": {"width": 800, "height": 400},
        "grande": {"width": 1600, "height": 800},
    }
    r = site_client.get(f"/medios/{mid}/mediana")
    assert r.mimetype == "image/webp"
    assert Image.open(io.BytesIO(r.data)).size == (800, 400)
    html = site_client.get(f"/medios/{mid}").get_data(as_text=True)
    assert "Generando variantes" not in html and "800 px" in html
    # El trabajador no deja rastro en la auditoría como si fuera una edición.
    with app.app_context():
        q = select(AuditLog.action).where(AuditLog.object_type == "Medio")
        assert db.session.scalars(q.execution_options(all_sites=True)).all() == ["crear"]


def test_no_agranda_imagenes_pequenas(app, site_client):
    # Con RQ_ASYNC=False el trabajo corre al encolarlo, pasando por RQ y Redis.
    mid = media_id(upload(site_client, ("hallulla.jpg", image_bytes(500, 250, "JPEG"))))
    assert all_media(app)[0].variants == {"miniatura": {"width": 320, "height": 160}}
    assert site_client.get(f"/medios/{mid}/grande").mimetype == "image/jpeg"


def test_variantes_fallidas_quedan_marcadas(app, site_client, monkeypatch):
    def broken(media):
        raise OSError("disco lleno")

    monkeypatch.setattr("app.media.tasks.make_variants", broken)
    mid = media_id(upload(site_client, ("a.png", image_bytes(400, 200))))
    assert all_media(app)[0].failed
    html = site_client.get(f"/medios/{mid}").get_data(as_text=True)
    assert "No se pudieron generar las variantes." in html


def test_biblioteca_filtros_y_busqueda(site_client):
    upload(site_client, ("marraqueta.png", image_bytes(400, 200)), ("carta.pdf", b"%PDF-1.4"))
    post(site_client, "/medios/1", {"alt_text": "Marraqueta recién horneada"})
    htmx = {"HX-Request": "true", "HX-Target": "medios"}

    def names(query):
        r = site_client.get(f"/medios/?{query}", headers=htmx)
        return [n for n in ["marraqueta.png", "carta.pdf"] if n in r.get_data(as_text=True)]

    assert names("") == ["marraqueta.png", "carta.pdf"]
    assert names("tipo=imagenes") == ["marraqueta.png"]
    assert names("tipo=documentos") == ["carta.pdf"]
    assert names("tipo=sin-usar") == ["marraqueta.png", "carta.pdf"]
    assert names("q=horneada") == ["marraqueta.png"]


def test_texto_alternativo_y_auditoria(app, site_client):
    mid = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    r = post(
        site_client,
        f"/medios/{mid}",
        {"alt_text": "  Pan amasado sobre la mesa  "},
        headers={"HX-Request": "true", "HX-Target": "detalle"},
    )
    assert 'value="Pan amasado sobre la mesa"' in r.get_data(as_text=True)
    assert all_media(app)[0].alt_text == "Pan amasado sobre la mesa"
    with app.app_context():
        q = select(AuditLog.action, AuditLog.object_label).where(AuditLog.object_type == "Medio")
        rows = db.session.execute(q.execution_options(all_sites=True)).all()
    assert [tuple(r) for r in rows] == [("crear", "pan.png"), ("editar", "pan.png")]


def test_eliminar_borra_registro_y_archivos(app, site_client):
    mid = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    with app.app_context():
        folder = files.folder(all_media(app)[0])
    assert (folder / "miniatura.webp").exists()
    r = post(site_client, f"/medios/{mid}/eliminar", {}, form_url=f"/medios/{mid}")
    assert r.status_code == 302
    assert all_media(app) == [] and not folder.exists()


def test_medio_de_otro_sitio_da_404(app, site_client):
    mid = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    create_site(site_client, "Clínica", "clinica")
    for url in [f"/medios/{mid}", f"/medios/{mid}/archivo", f"/medios/{mid}/mediana"]:
        assert site_client.get(url).status_code == 404, url
    assert post(site_client, f"/medios/{mid}", {"alt_text": "x"}, form_url="/").status_code == 404
    r = post(site_client, f"/medios/{mid}/eliminar", {}, form_url="/")
    assert r.status_code == 404
    html = site_client.get("/medios/").get_data(as_text=True)
    assert "pan.png" not in html
    assert "pan.png" not in site_client.get("/medios/selector").get_data(as_text=True)
    assert len(all_media(app)) == 1
