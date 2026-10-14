"""Entradas de ejemplo generadas desde el esquema, para probar plantillas sin contenido real."""

from datetime import date

from markupsafe import Markup
from sqlalchemy import select

from app.content.models import ContentType
from app.extensions import db
from app.media.models import Media

COUNT = 3


def media_view(m):
    return {"id": m.id, "nombre": m.filename, "alt": m.alt_text, "ancho": m.width, "alto": m.height}


def value_for(key, prop, i, depth):
    match prop["x-type"]:
        case "text":
            text = f"{prop['title']} de ejemplo {i}"
            return text[: prop.get("maxLength", len(text))].ljust(prop.get("minLength", 0), "·")
        case "slug":
            return f"ejemplo-{i}"
        case "rich":
            return Markup(f"<p>Texto de ejemplo para {prop['title'].lower()}.</p>")
        case "number":
            low, high = prop.get("minimum", 0), prop.get("maximum")
            value = max(low, 1000 * i)
            return min(value, high) if high is not None else value
        case "date":
            return date.today().isoformat()
        case "bool":
            return i % 2 == 1
        case "image":
            m = db.session.scalar(
                select(Media).where(Media.mime.startswith("image/")).order_by(Media.id)
            )
            return media_view(m) if m else None
        case "relation":
            ct = db.session.scalar(select(ContentType).where(ContentType.id == prop["x-ref"]))
            return make(ct, 1, depth + 1)[0] if ct and depth == 0 else None


def make(ct, count=COUNT, depth=0):
    return [
        {key: value_for(key, prop, i, depth) for key, prop in ct.fields}
        | {"id": -i, "slug": f"ejemplo-{i}", "modelo": ct.key, "actualizada": None}
        for i in range(1, count + 1)
    ]


def entries(ct, orden, limit, filtros):
    items = [e for e in make(ct) if all(e.get(k) == v for k, v in filtros.items())]
    if orden:
        key = orden.lstrip("-")
        items.sort(key=lambda e: (e.get(key) is None, e.get(key)), reverse=orden.startswith("-"))
    return items[:limit]
