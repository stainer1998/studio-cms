"""Funciones y filtros que pueden usar las plantillas de los sitios (nombres en español).

Las plantillas reciben diccionarios de solo lectura, nunca objetos del ORM:
- entrada: los campos del modelo más `id`, `slug`, `modelo` y `actualizada`. Las relaciones
  se resuelven un nivel (otra entrada) y los campos imagen pasan a ser un medio.
- medio: `id`, `nombre`, `alt`, `ancho`, `alto`.
"""

from datetime import date, datetime

from markupsafe import Markup
from sqlalchemy import select

from app.content.models import ContentType, Entry
from app.extensions import db
from app.media.models import VARIANTS, Media
from app.templating import sample
from app.templating.sample import media_view

MAX_ENTRIES = 500
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class TemplateDataError(Exception):
    """Error de uso de una función del CMS; su mensaje se muestra tal cual al administrador."""


# --- Filtros ---------------------------------------------------------------------------


def moneda(value):
    """Pesos chilenos: sin decimales y con punto como separador de miles."""
    if value is None or value == "":
        return ""
    n = round(float(value))
    return f"{'-' if n < 0 else ''}${abs(n):,}".replace(",", ".")


def fecha(value, formato="corto"):
    """`corto`: 13-10-2026. `largo`: 13 de octubre de 2026."""
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        value = value.date()
    if formato == "largo":
        return f"{value.day} de {MONTHS[value.month - 1]} de {value.year}"
    return value.strftime("%d-%m-%Y")


FILTERS = {"moneda": moneda, "fecha": fecha}


# --- Funciones -------------------------------------------------------------------------


def entry_view(entry, ct, related=None, media=None):
    related, media = related or {}, media or {}
    view = {}
    for key, prop in ct.fields:
        value = entry.data.get(key)
        match prop["x-type"]:
            case "rich":
                value = Markup(value or "")  # ya sanitizado con nh3 al guardar
            case "relation":
                value = related.get(value)
            case "image":
                value = media.get(value)
        view[key] = value
    return view | {
        "id": entry.id,
        "slug": entry.slug,
        "modelo": ct.key,
        "actualizada": entry.updated_at,
    }


def build(sample_data=False, media_url_for=None):
    """Funciones de una ejecución. `media_url_for(id, variante)` cambia entre vista previa
    y exportación; el resto del motor es el mismo para ambas."""

    def get_type(modelo):
        ct = db.session.scalar(select(ContentType).where(ContentType.key == modelo))
        if ct is None:
            raise TemplateDataError(f"No existe el modelo «{modelo}» en este sitio.")
        return ct

    def ready(ids):
        if not ids:
            return {}
        q = select(Entry).where(Entry.id.in_(ids), Entry.status == "listo")
        return {e.id: e for e in db.session.scalars(q)}

    def views(ct, entries):
        rel_types = {k: p["x-ref"] for k, p in ct.fields if p["x-type"] == "relation"}
        img_keys = [k for k, p in ct.fields if p["x-type"] == "image"]
        rel = ready({e.data[k] for e in entries for k in rel_types if k in e.data})
        img_ids = {e.data[k] for e in entries for k in img_keys if k in e.data}
        media = {}
        if img_ids:
            query = select(Media).where(Media.id.in_(img_ids))
            media = {m.id: media_view(m) for m in db.session.scalars(query)}
        related = {i: entry_view(e, e.content_type, media=media) for i, e in rel.items()}
        return [entry_view(e, ct, related, media) for e in entries]

    def entradas(modelo, orden=None, limite=None, **filtros):
        ct = get_type(modelo)
        limit = min(int(limite), MAX_ENTRIES) if limite is not None else MAX_ENTRIES
        if sample_data:
            return sample.entries(ct, orden, limit, filtros)
        q = select(Entry).where(Entry.content_type_id == ct.id, Entry.status == "listo")
        for key, value in filtros.items():
            q = q.where(Entry.slug == value if key == "slug" else Entry.data.contains({key: value}))
        if orden:
            key = orden.lstrip("-")
            column = Entry.updated_at if key == "actualizada" else Entry.data[key]
            q = q.order_by(column.desc() if orden.startswith("-") else column.asc())
        q = q.order_by(Entry.id).limit(limit)
        return views(ct, db.session.scalars(q).all())

    def entrada(modelo, slug):
        found = entradas(modelo, limite=1, slug=slug)
        if not found and sample_data:
            found = entradas(modelo, limite=1)
        return found[0] if found else None

    def url_entrada(entrada):
        # ponytail: sin rutas todavía; en H5 devuelve la URL según las rutas del sitio.
        return "#"

    def media_url(media, variante="mediana"):
        if not media:
            return ""
        if variante not in VARIANTS and variante != "original":
            names = ", ".join([*VARIANTS, "original"])
            raise TemplateDataError(f"La variante «{variante}» no existe. Usa una de: {names}.")
        media_id = media["id"] if isinstance(media, dict) else int(media)
        return media_url_for(media_id, variante)

    return {
        "entradas": entradas,
        "entrada": entrada,
        "url_entrada": url_entrada,
        "media_url": media_url,
    }
