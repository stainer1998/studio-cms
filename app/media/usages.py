"""Registro de dónde se usa cada medio (RF-15). Se recalcula cada vez que cambia `entry.data`."""

import re

from sqlalchemy import delete, select

from app.extensions import db
from app.media.models import Media, MediaUsage

# Las imágenes del texto enriquecido apuntan a /medios/<id>/<variante> (ver el selector).
RICH_SRC = re.compile(r'<img[^>]+src="/medios/(\d+)/')
# En plantillas solo se pueden detectar los ids escritos a mano, como media_url(12).
TEMPLATE_MEDIA = re.compile(r"media_url\(\s*(\d+)")


def media_ids(entry):
    ids = set()
    for key, prop in entry.content_type.fields:
        value = entry.data.get(key)
        if prop["x-type"] == "image" and isinstance(value, int):
            ids.add(value)
        elif prop["x-type"] == "rich" and value:
            ids.update(int(i) for i in RICH_SRC.findall(value))
    return ids


def replace_usages(ids, owner_column, owner_id):
    """Reemplaza los usos de una entrada o plantilla. Solo cuenta medios del sitio activo."""
    db.session.execute(delete(MediaUsage).where(owner_column == owner_id))
    if ids:
        existing = db.session.scalars(select(Media.id).where(Media.id.in_(ids)))
        db.session.add_all(MediaUsage(media_id=i, **{owner_column.key: owner_id}) for i in existing)


def sync_usages(entry):
    replace_usages(media_ids(entry), MediaUsage.entry_id, entry.id)


def sync_template_usages(template):
    ids = {int(i) for i in TEMPLATE_MEDIA.findall(template.source)}
    replace_usages(ids, MediaUsage.template_id, template.id)
