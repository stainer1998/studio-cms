"""Registro de dónde se usa cada medio (RF-15). Se recalcula cada vez que cambia `entry.data`."""

import re

from sqlalchemy import delete, select

from app.extensions import db
from app.media.models import Media, MediaUsage

# Las imágenes del texto enriquecido apuntan a /medios/<id>/<variante> (ver el selector).
RICH_SRC = re.compile(r'<img[^>]+src="/medios/(\d+)/')


def media_ids(entry):
    ids = set()
    for key, prop in entry.content_type.fields:
        value = entry.data.get(key)
        if prop["x-type"] == "image" and isinstance(value, int):
            ids.add(value)
        elif prop["x-type"] == "rich" and value:
            ids.update(int(i) for i in RICH_SRC.findall(value))
    return ids


def sync_usages(entry):
    """Reemplaza los usos de la entrada. Solo cuenta medios que existen en el sitio activo."""
    db.session.execute(delete(MediaUsage).where(MediaUsage.entry_id == entry.id))
    ids = media_ids(entry)
    if ids:
        existing = db.session.scalars(select(Media.id).where(Media.id.in_(ids)))
        db.session.add_all(MediaUsage(media_id=i, entry_id=entry.id) for i in existing)
