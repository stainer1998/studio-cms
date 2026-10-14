from datetime import date

from app.templating.functions import fecha, moneda
from tests.conftest import (
    add_field,
    create_site,
    create_template,
    image_bytes,
    media_id,
    post,
    preview,
    product_type,
    save_entry,
    save_template,
    upload,
)


def test_moneda_y_fecha():
    assert moneda(0) == "$0"
    assert moneda(3500) == "$3.500"
    assert moneda(1234567.6) == "$1.234.568"
    assert moneda(-1500) == "-$1.500"
    assert moneda(None) == ""
    assert fecha("2026-10-13") == "13-10-2026"
    assert fecha(date(2026, 10, 3), "largo") == "3 de octubre de 2026"
    assert fecha(None) == ""


def test_sandbox_bloquea_atributos_internos(site_client):
    tid = create_template(site_client, "prueba.html")
    html = preview(site_client, tid, "{{ ''.__class__.__mro__ }}")
    assert "intentó acceder a «__class__», que no está permitido en el sandbox" in html
    html = preview(site_client, tid, "Hola\n{{ entradas.__globals__ }}")
    assert "«__globals__»" in html
    # Fuera de las funciones del CMS no hay nada: ni config, ni request, ni el ORM.
    assert preview(site_client, tid, "[{{ config }}{{ request }}{{ db }}]") == "[]"


def catalog(client):
    """Categoría Panes y tres productos: dos listos y un borrador."""
    cat, prod = product_type(client)
    save_entry(client, f"/contenido/{cat}/nueva", nombre="Panes", status="listo")
    for nombre, precio, destacado, status in [
        ("Marraqueta", "1200", "on", "listo"),
        ("Pan de masa madre", "3500", "on", "listo"),
        ("Hallulla <b>", "900", "", "listo"),
        ("Queque", "5000", "on", "borrador"),
    ]:
        fields = dict(nombre=nombre, precio=precio, categoria="1", status=status)
        if destacado:  # un checkbox cuenta como marcado si viene en el formulario
            fields["destacado"] = "on"
        save_entry(
            client,
            f"/contenido/{prod}/nueva",
            descripcion="<p>Miga <strong>abierta</strong></p>",
            **fields,
        )
    return cat, prod


def test_entradas_solo_listas_con_filtros_orden_y_limite(site_client):
    catalog(site_client)
    tid = create_template(site_client, "listado.html")
    src = (
        "{% for p in entradas('producto', orden='-precio', limite=2) %}"
        "{{ p.nombre }}={{ p.precio | moneda }};{% endfor %}"
    )
    assert preview(site_client, tid, src) == "Pan de masa madre=$3.500;Marraqueta=$1.200;"
    src = (
        "{% for p in entradas('producto', destacado=True, orden='nombre') %}"
        "{{ p.slug }} {% endfor %}"
    )
    assert preview(site_client, tid, src) == "marraqueta pan-de-masa-madre "
    src = "{{ entradas('producto') | length }}"
    assert preview(site_client, tid, src) == "3"  # el borrador no aparece

    src = "{% set p = entrada('producto', 'hallulla-b') %}{{ p.nombre }}|{{ p.categoria.nombre }}"
    assert preview(site_client, tid, src) == "Hallulla &lt;b&gt;|Panes"
    src = (
        "{{ entrada('producto', 'pan-de-masa-madre').descripcion }}"
        "{{ entrada('producto', 'queque') }}"
    )
    assert preview(site_client, tid, src) == "<p>Miga <strong>abierta</strong></p>None"
    assert preview(site_client, tid, "{{ url_entrada(entradas('producto')[0]) }}") == "#"


def test_errores_de_las_funciones_con_mensaje_claro(site_client):
    tid = create_template(site_client, "x.html")
    html = preview(site_client, tid, "\n\n{{ entradas('servicio') }}")
    assert "No existe el modelo «servicio» en este sitio." in html
    html = preview(site_client, tid, "{{ media_url(1, 'gigante') }}")
    assert "La variante «gigante» no existe" in html


def test_media_url_y_campo_imagen(site_client):
    _, prod = product_type(site_client)
    add_field(site_client, prod, "foto", "Foto", "image")
    mid = media_id(upload(site_client, ("pan.png", image_bytes(400, 200))))
    post(site_client, f"/medios/{mid}", {"alt_text": "Pan amasado"})
    save_entry(
        site_client,
        f"/contenido/{prod}/nueva",
        nombre="Pan",
        precio="1",
        foto=str(mid),
        status="listo",
    )
    tid = create_template(site_client, "x.html")
    src = (
        "{% set p = entradas('producto')[0] %}"
        '<img src="{{ media_url(p.foto, \'miniatura\') }}" alt="{{ p.foto.alt }}">'
        "{{ media_url(p.foto) }} {{ media_url("
        + str(mid)
        + ", 'original') }} [{{ media_url(None) }}]"
    )
    assert preview(site_client, tid, src) == (
        f'<img src="/medios/{mid}/miniatura" alt="Pan amasado">'
        f"/medios/{mid}/mediana /medios/{mid}/archivo []"
    )


def test_datos_de_ejemplo_desde_el_esquema(site_client):
    _, prod = product_type(site_client)
    add_field(site_client, prod, "stock", "Stock", "number", minimum="5", maximum="1500")
    tid = create_template(site_client, "x.html")
    src = (
        "{% for p in entradas('producto') %}"
        "{{ p.nombre }}/{{ p.slug }}/{{ p.precio }}/{{ p.stock }}/{{ p.categoria.nombre }};"
        "{% endfor %}"
    )
    assert preview(site_client, tid, src) == ""  # sin entradas reales
    assert preview(site_client, tid, src, datos="ejemplo") == (
        "Nombre de ejemplo 1/ejemplo-1/1000/1000/Nombre de ejemplo 1;"
        "Nombre de ejemplo 2/ejemplo-2/2000/1500/Nombre de ejemplo 1;"
        "Nombre de ejemplo 3/ejemplo-3/3000/1500/Nombre de ejemplo 1;"
    )


def test_herencia_parciales_y_cache_invalidada_al_guardar(site_client):
    cabecera = create_template(site_client, "parciales/cabecera.html", "Los Aromos")
    create_template(
        site_client,
        "base.html",
        "<header>{% include 'parciales/cabecera.html' %}</header>"
        "<main>{% block contenido %}{% endblock %}</main>",
    )
    source = "{% extends 'base.html' %}{% block contenido %}Productos{% endblock %}"
    listado = create_template(site_client, "productos/listado.html", source)
    expected = "<header>Los Aromos</header><main>Productos</main>"
    assert preview(site_client, listado, source) == expected
    save_template(site_client, cabecera, "Panadería Los Aromos")
    assert "<header>Panadería Los Aromos</header>" in preview(site_client, listado, source)


def test_plantillas_de_otro_sitio_no_se_pueden_incluir(site_client):
    create_template(site_client, "parciales/pie.html", "Pie de Los Aromos")
    create_site(site_client, "Clínica", "clinica")
    tid = create_template(site_client, "inicio.html")
    r = save_template(site_client, tid, "{% include 'parciales/pie.html' %}")
    assert r.status_code == 422
    assert "No existe la plantilla «parciales/pie.html»." in r.get_data(as_text=True)
    html = preview(site_client, tid, "{% include 'parciales/pie.html' %}")
    assert "No existe la plantilla «parciales/pie.html»." in html
    assert "Pie de Los Aromos" not in html


def test_errores_de_sintaxis_en_espanol():
    from app.templating.engine import syntax_message

    assert (
        syntax_message("expected token 'name', got '{'") == "se esperaba «name» y se encontró «{»."
    )
    assert syntax_message("Encountered unknown tag 'endfro'.") == "etiqueta desconocida «endfro»."
    assert (
        syntax_message(
            "Encountered unknown tag 'endblock'. Jinja was looking for the following tags: "
            "'endfor' or 'else'. The innermost block that needs to be closed is 'for'."
        )
        == "«endblock» no va aquí: antes hay que cerrar el bloque «for» con «endfor» o «else»."
    )
    assert (
        syntax_message(
            "Encountered unknown tag 'endblock'. You probably made a nesting mistake. Jinja is "
            "expecting this tag, but currently looking for 'endfor' or 'else'. The innermost block "
            "that needs to be closed is 'for'."
        )
        == "«endblock» no va aquí: antes hay que cerrar el bloque «for» con «endfor» o «else»."
    )
    assert syntax_message("un mensaje nuevo de Jinja") == "un mensaje nuevo de Jinja"
