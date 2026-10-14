from sqlalchemy import select, update

from app.extensions import db
from app.templating.models import Template, TemplateVersion
from tests.conftest import (
    create_site,
    create_template,
    csrf,
    image_bytes,
    media_id,
    post,
    save_template,
    upload,
)


def rows(app, model):
    with app.app_context():
        q = select(model).order_by(model.id).execution_options(all_sites=True)
        return db.session.scalars(q).all()


def test_crear_con_ruta_valida_y_unica(app, site_client):
    for bad in ["Productos/Listado.html", "listado", "/base.html", "a//b.html", "../x.html"]:
        r = post(site_client, "/plantillas/nueva", {"path": bad})
        assert r.status_code == 422, bad
    create_template(site_client, "productos/listado.html")
    r = post(site_client, "/plantillas/nueva", {"path": "productos/listado.html"})
    assert "Ya existe una plantilla con esa ruta." in r.get_data(as_text=True)
    html = site_client.get("/plantillas/1").get_data(as_text=True)
    assert "productos/" in html and "listado.html" in html
    assert [t.path for t in rows(app, Template)] == ["productos/listado.html"]


def test_error_de_sintaxis_con_linea_y_sin_guardar(app, site_client):
    tid = create_template(site_client, "listado.html", "<h1>Productos</h1>")
    broken = "<h1>Productos</h1>\n{% for p in entradas('producto') %}\n  {{ p.nombre }}\n"
    r = save_template(site_client, tid, broken)
    html = r.get_data(as_text=True)
    assert r.status_code == 422
    assert "Error de sintaxis en la línea 3" in html
    assert "la plantilla termina sin cerrar un bloque; falta «endfor» o «else»." in html
    assert "{{ p.nombre }}" in html  # lo escrito sigue en el editor
    assert rows(app, Template)[0].source == "<h1>Productos</h1>"
    assert len(rows(app, TemplateVersion)) == 2  # creación y primer guardado

    r = site_client.post(
        "/plantillas/validar",
        json={"source": "ok\n{{ p.nombre }", "path": "listado.html"},
        headers={"X-CSRFToken": csrf(site_client, f"/plantillas/{tid}")},
    )
    assert r.get_json()["errors"][0]["line"] == 2


def test_versiones_y_restaurar(app, site_client):
    tid = create_template(site_client, "x.html", "uno")
    save_template(site_client, tid, "dos")
    save_template(site_client, tid, "dos")  # sin cambios no crea versión
    versions = rows(app, TemplateVersion)
    assert [v.source for v in versions] == ["", "uno", "dos"]
    html = site_client.get(f"/plantillas/{tid}/versiones?v={versions[1].id}").get_data(as_text=True)
    assert "uno" in html and "Restaurar esta versión" in html
    url = f"/plantillas/{tid}/versiones/{versions[1].id}/restaurar"
    post(site_client, url, {}, form_url=f"/plantillas/{tid}/versiones")
    assert rows(app, Template)[0].source == "uno"
    assert [v.source for v in rows(app, TemplateVersion)][-1] == "uno"


def test_modo_visual_es_solo_lectura(app, site_client):
    tid = create_template(site_client, "inicio.html", "<section>Generado</section>")
    with app.app_context():
        q = update(Template).values(mode="visual").execution_options(all_sites=True)
        db.session.execute(q)
        db.session.commit()
    html = site_client.get(f"/plantillas/{tid}").get_data(as_text=True)
    assert "Modo principal: Visual" in html and " readonly" in html
    assert "código generado es de solo lectura" in html
    r = save_template(site_client, tid, "cambio a mano")
    assert r.status_code == 409
    assert rows(app, Template)[0].source == "<section>Generado</section>"

    post(site_client, f"/plantillas/{tid}/convertir", {}, form_url=f"/plantillas/{tid}")
    assert rows(app, Template)[0].mode == "code"
    assert save_template(site_client, tid, "cambio a mano").status_code == 302


def test_renombrar_y_eliminar_avisan_referencias(app, site_client):
    pie = create_template(site_client, "pie.html", "Pie")
    create_template(site_client, "base.html", "{% include 'pie.html' %}")
    url = f"/plantillas/{pie}/renombrar"
    r = post(site_client, url, {"path": "parciales/pie.html"}, form_url=f"/plantillas/{pie}")
    html = site_client.get(r.location).get_data(as_text=True)
    assert "Actualiza las referencias a «pie.html» en: base.html." in html

    save_template(site_client, 2, "{% include 'parciales/pie.html' %}")
    html = site_client.get(f"/plantillas/{pie}/eliminar").get_data(as_text=True)
    assert "La usan en" in html and "base.html" in html
    post(site_client, f"/plantillas/{pie}/eliminar", {}, form_url=f"/plantillas/{pie}/eliminar")
    assert [t.path for t in rows(app, Template)] == ["base.html"]


def test_medio_usado_en_plantilla(site_client):
    mid = media_id(upload(site_client, ("logo.png", image_bytes(400, 200))))
    tid = create_template(site_client, "base.html", f'<img src="{{{{ media_url({mid}) }}}}">')
    html = site_client.get(f"/medios/{mid}").get_data(as_text=True)
    assert "Plantilla" in html and f"/plantillas/{tid}" in html
    assert "No se puede eliminar mientras esté en uso." in html
    save_template(site_client, tid, "<p>Sin logo</p>")
    assert "Sin usar." in site_client.get(f"/medios/{mid}").get_data(as_text=True)


def test_politicas_de_seguridad_del_editor_y_la_vista_previa(site_client):
    tid = create_template(site_client, "x.html", "<p>Hola</p>")
    editor = site_client.get(f"/plantillas/{tid}").headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in editor and "script-src" not in editor
    r = post(
        site_client,
        f"/plantillas/{tid}/vista-previa",
        {"source": "<script>alert(1)</script>"},
        form_url=f"/plantillas/{tid}",
    )
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'self'" in csp
    other = site_client.get("/medios/").headers["Content-Security-Policy"]
    assert "unsafe-inline" not in other and "frame-ancestors 'none'" in other


def test_plantilla_de_otro_sitio_da_404(app, site_client):
    tid = create_template(site_client, "base.html", "Hola")
    create_site(site_client, "Clínica", "clinica")
    for url in [
        f"/plantillas/{tid}",
        f"/plantillas/{tid}/versiones",
        f"/plantillas/{tid}/eliminar",
    ]:
        assert site_client.get(url).status_code == 404, url
    for url in [
        f"/plantillas/{tid}",
        f"/plantillas/{tid}/vista-previa",
        f"/plantillas/{tid}/renombrar",
        f"/plantillas/{tid}/convertir",
        f"/plantillas/{tid}/versiones/1/restaurar",
    ]:
        assert (
            post(site_client, url, {"source": "x", "path": "y.html"}, form_url="/").status_code
            == 404
        )
    assert f"/plantillas/{tid}" not in site_client.get("/plantillas/nueva").get_data(as_text=True)
    assert len(rows(app, Template)) == 1
