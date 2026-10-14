"""Trabajos en segundo plano de medios (RNF-11). Los ejecuta `rq worker`, nunca la petición."""

import logging

from flask import current_app, has_app_context
from redis import Redis
from rq import Queue
from sqlalchemy import update

from app.extensions import db
from app.media.files import make_variants
from app.media.models import Media

log = logging.getLogger(__name__)


def enqueue(func, *args):
    """Encola en RQ. Con RQ_ASYNC=False (pruebas) el trabajo corre en el mismo proceso."""
    queue = Queue(
        connection=Redis.from_url(current_app.config["REDIS_URL"]),
        is_async=current_app.config["RQ_ASYNC"],
    )
    return queue.enqueue(func, *args)


def generate_variants(media_id):
    if has_app_context():
        return _generate_variants(media_id)
    from app import create_app

    with create_app().app_context():
        return _generate_variants(media_id)


def _generate_variants(media_id):
    # El trabajador no tiene sitio activo: se salta el filtro de forma explícita.
    media = db.session.get(Media, media_id, execution_options={"all_sites": True})
    if media is None:
        return  # se eliminó antes de que el trabajo corriera
    try:
        variants = make_variants(media)
    except Exception:
        log.exception("No se pudieron generar las variantes del medio %s", media_id)
        variants = {"error": "No se pudieron generar las variantes."}
    # UPDATE directo: no es una edición del administrador y no debe quedar en la auditoría.
    db.session.execute(
        update(Media).where(Media.id == media_id).values(variants=variants),
        execution_options={"all_sites": True},
    )
    db.session.commit()
