"""Biblioteca de medios: subida, ficha, texto alternativo y archivos (RF-13 a RF-15)."""

from flask import Blueprint, abort, current_app, flash, render_template, request, send_file, url_for
from sqlalchemy import exists, or_, select

from app.core.htmx import go
from app.extensions import db
from app.media import files
from app.media.models import VARIANTS, Media, MediaUsage
from app.media.tasks import enqueue, generate_variants

bp = Blueprint("media", __name__, url_prefix="/medios")

FILTERS = {"": "Todos", "imagenes": "Imágenes", "documentos": "Documentos", "sin-usar": "Sin usar"}
in_use = exists().where(MediaUsage.media_id == Media.id)


def get_media(media_id):
    return db.one_or_404(select(Media).where(Media.id == media_id))


def search(kind="", q="", images_only=False):
    query = select(Media).order_by(Media.created_at.desc(), Media.id.desc())
    if kind == "imagenes" or images_only:
        query = query.where(Media.mime.startswith("image/"))
    elif kind == "documentos":
        query = query.where(~Media.mime.startswith("image/"))
    elif kind == "sin-usar":
        query = query.where(~in_use)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Media.filename.ilike(like), Media.alt_text.ilike(like)))
    return db.session.scalars(query).all()


def used_ids():
    return set(db.session.scalars(select(MediaUsage.media_id).distinct()))


def usages_of(media):
    q = select(MediaUsage).where(MediaUsage.media_id == media.id).order_by(MediaUsage.entry_id)
    return db.session.scalars(q).unique().all()


def detail_context(media):
    return dict(media=media, usages=usages_of(media), VARIANTS=VARIANTS)


@bp.route("/")
@bp.route("/<int:media_id>")
def index(media_id=None):
    selected = get_media(media_id) if media_id else None
    if selected and request.headers.get("HX-Target") == "detalle":
        return render_template("media/_detail.html", **detail_context(selected))
    kind = request.args.get("tipo", "")
    kind = kind if kind in FILTERS else ""
    q = request.args.get("q", "").strip()
    ctx = dict(items=search(kind, q), used=used_ids(), kind=kind, q=q, selected=selected)
    if request.headers.get("HX-Target") == "medios":
        return render_template("media/_grid.html", **ctx)
    detail = detail_context(selected) if selected else {}
    return render_template("media/library.html", FILTERS=FILTERS, **ctx, **detail)


@bp.route("/subir", methods=["POST"])
def upload():
    saved = []
    max_bytes = current_app.config["MEDIA_MAX_BYTES"]
    uploads = [f for f in request.files.getlist("archivos") if f.filename]
    if not uploads:
        flash("Elige al menos un archivo.", "error")
    for upload in uploads:
        name = upload.filename.rsplit("/", 1)[-1][:200]
        upload.stream.seek(0, 2)
        size = upload.stream.tell()
        if size > max_bytes:
            flash(f"«{name}» supera el tamaño máximo de {max_bytes // 2**20} MB.", "error")
            continue
        try:
            mime, width, height = files.detect(upload.stream)
        except files.InvalidFile as e:
            flash(f"«{name}» {e}.", "error")
            continue
        media = Media(filename=name, mime=mime, size=size, width=width, height=height)
        media.variants = None if media.is_image else {}
        db.session.add(media)
        db.session.flush()
        files.store(media, upload.stream)
        db.session.commit()
        if media.is_image:
            enqueue(generate_variants, media.id)
        saved.append(media)
    if saved:
        flash(f"Archivos subidos: {len(saved)}.")
        return go(url_for("media.index", media_id=saved[-1].id))
    return go(url_for("media.index"))


@bp.route("/<int:media_id>", methods=["POST"])
def update(media_id):
    media = get_media(media_id)
    media.alt_text = request.form.get("alt_text", "").strip()[:300]
    db.session.commit()
    flash("Texto alternativo guardado.")
    if request.headers.get("HX-Request"):
        return render_template("media/_detail.html", saved=True, **detail_context(media))
    return go(url_for("media.index", media_id=media.id))


@bp.route("/<int:media_id>/eliminar", methods=["POST"])
def delete(media_id):
    media = get_media(media_id)
    if usages_of(media):
        flash(f"«{media.filename}» está en uso y no se puede eliminar.", "error")
        return go(url_for("media.index", media_id=media.id))
    db.session.delete(media)
    db.session.commit()
    files.remove(media)
    flash(f"«{media.filename}» eliminado.")
    return go(url_for("media.index"))


@bp.route("/<int:media_id>/archivo")
@bp.route("/<int:media_id>/<variant>")
def file(media_id, variant=None):
    """Sirve el archivo. Una variante aún no generada responde con el original (RF-14)."""
    media = get_media(media_id)
    if variant is not None and variant not in VARIANTS:
        abort(404)
    if variant and media.has_variant(variant):
        return send_file(files.variant_path(media, variant), mimetype="image/webp")
    return send_file(files.original_path(media), mimetype=media.mime, download_name=media.filename)


@bp.route("/selector")
def picker():
    """Imágenes para el selector del formulario de entradas y de Tiptap."""
    q = request.args.get("q", "").strip()
    return render_template("media/_picker.html", items=search(q=q, images_only=True), q=q)


@bp.app_template_filter("tamano")
def size_label(size):
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / 1024 / 1024:.1f} MB".replace(".", ",")
