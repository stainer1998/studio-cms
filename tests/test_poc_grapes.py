"""Prueba de concepto de GrapesJS (rama poc/grapesjs-jinja): el Jinja que exporta el bloque
«Lista de entradas» es válido, y el lienzo y la vista previa salen del mismo motor."""

from tests.conftest import create_template, csrf, preview
from tests.test_templating_engine import catalog

LIST = (
    '<section class="cms-lista">\n'
    '{% for p in entradas("producto", destacado=True, orden="-precio", limite=2) %}\n'
    '<article class="cms-lista__item">\n<h3>{{ p.nombre }}</h3>\n'
    "<p>{{ p.precio | moneda }}</p>\n"
    '<a href="{{ url_entrada(p) }}">Ver detalle</a>\n</article>\n{% endfor %}\n</section>\n'
)


def test_lista_exportada_es_valida_y_el_lienzo_coincide_con_la_vista_previa(site_client):
    catalog(site_client)
    tid = create_template(site_client, "paginas/inicio.html")
    token = csrf(site_client, f"/plantillas/{tid}/visual-poc")
    r = site_client.post(
        f"/plantillas/{tid}/visual-poc", json={"source": LIST}, headers={"X-CSRFToken": token}
    )
    assert r.get_json() == {"errors": []}
    inner = LIST.split("\n", 1)[1].rsplit("</section>", 1)[0]
    for datos in ["reales", "ejemplo"]:
        canvas = site_client.post(
            "/plantillas/fragmento",
            json={"source": inner, "datos": datos},
            headers={"X-CSRFToken": token},
        ).get_data(as_text=True)
        page = preview(site_client, tid, LIST, datos)
        assert (
            page == f'<section class="cms-lista">\n{canvas}\n</section>'
        )  # Jinja quita el último salto
    assert "Pan de masa madre" in canvas or "ejemplo" in canvas


def test_texto_con_llaves_de_jinja_no_se_puede_guardar(site_client):
    tid = create_template(site_client, "paginas/x.html")
    token = csrf(site_client, f"/plantillas/{tid}/visual-poc")
    r = site_client.post(
        f"/plantillas/{tid}/visual-poc",
        json={"source": "<p>Oferta {% if x %}</p>"},
        headers={"X-CSRFToken": token},
    )
    assert r.status_code == 422  # hallazgo para H7: el texto estático debe escaparse
