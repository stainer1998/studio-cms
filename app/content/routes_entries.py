"""Entradas: lista, formulario generado desde el modelo y versiones (RF-09 a RF-12)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import Text, cast, func, select

from app.content import fields as F
from app.content.models import STATUSES, Entry, EntryVersion
from app.content.routes_types import all_types, get_type
from app.core.htmx import go
from app.extensions import db
from app.media.models import Media
from app.media.usages import sync_usages

bp = Blueprint("entries", __name__, url_prefix="/contenido")


def get_entry(entry_id):
    return db.one_or_404(select(Entry).where(Entry.id == entry_id))


def type_counts():
    q = select(Entry.content_type_id, func.count(Entry.id)).group_by(Entry.content_type_id)
    return dict(db.session.execute(q).all())


def relation_options(ct):
    """Entradas elegibles para cada campo de relación: {clave: [(id, título)]}."""
    options = {}
    for key, prop in ct.fields:
        if prop["x-type"] == "relation":
            q = select(Entry).where(Entry.content_type_id == prop["x-ref"]).order_by(Entry.id)
            options[key] = [(e.id, e.title) for e in db.session.scalars(q)]
    return options


def image_fields(ct, data):
    """Imágenes elegidas en los campos imagen: {clave: {id: Media}}. Solo del sitio activo."""
    keys = [k for k, p in ct.fields if p["x-type"] == "image" and k in data]
    ids = {data[k] for k in keys}
    query = select(Media).where(Media.id.in_(ids), Media.mime.startswith("image/"))
    found = {m.id: m for m in db.session.scalars(query)} if ids else {}
    return {k: {data[k]: found[data[k]]} if data[k] in found else {} for k in keys}


@bp.route("/")
def index():
    types = all_types()
    if types:
        return redirect(url_for("entries.list_entries", type_id=types[0].id))
    return render_template("content/entries_empty.html")


@bp.route("/<int:type_id>/")
def list_entries(type_id):
    ct = get_type(type_id)
    q = request.args.get("q", "").strip()
    status = request.args.get("estado", "")
    query = select(Entry).where(Entry.content_type_id == ct.id).order_by(Entry.updated_at.desc())
    if q:
        query = query.where(func.lower(cast(Entry.data, Text)).contains(q.lower(), autoescape=True))
    if status in STATUSES:
        query = query.where(Entry.status == status)
    entries = db.session.scalars(query).all()
    ctx = dict(ct=ct, entries=entries, q=q, status=status, STATUSES=STATUSES)
    if request.headers.get("HX-Request"):
        return render_template("content/_entries_table.html", **ctx)
    return render_template("content/entries.html", types=all_types(), counts=type_counts(), **ctx)


def save(ct, entry):
    """Valida y guarda la entrada (y su versión). Devuelve los errores por campo."""
    data, errors = F.parse_form(ct, request.form)
    for key, message in F.validate(ct.schema, data).items():
        errors.setdefault(key, message)

    slug_key = ct.slug_field
    slug = data.get(slug_key) if slug_key else None
    if slug and slug_key not in errors:
        taken = select(Entry.id).where(Entry.content_type_id == ct.id, Entry.slug == slug)
        if entry.id:
            taken = taken.where(Entry.id != entry.id)
        if db.session.scalar(taken):
            errors[slug_key] = "Ya existe una entrada con ese slug en este modelo."

    for key, options in relation_options(ct).items():
        if key in data and data[key] not in {i for i, _ in options}:
            errors[key] = "Elige una entrada del modelo relacionado."

    images = image_fields(ct, data)
    for key in images:
        if data[key] not in images[key]:
            errors[key] = "Elige una imagen de la biblioteca de Medios."

    status = request.form.get("status")
    if errors or status not in STATUSES:
        return errors or {"status": "Elige un estado."}, data

    entry.data, entry.slug, entry.status = data, slug, status
    if not entry.id:
        db.session.add(entry)
        db.session.flush()
    db.session.add(EntryVersion(entry_id=entry.id, data=data, status=status))
    sync_usages(entry)
    db.session.commit()
    return {}, data


def render_form(ct, entry, data, errors=None, status=200):
    return render_template(
        "content/entry_form.html",
        ct=ct,
        entry=entry,
        data=data,
        errors=errors or {},
        relations=relation_options(ct),
        images={m.id: m for ms in image_fields(ct, data).values() for m in ms.values()},
        STATUSES=STATUSES,
        TYPES=F.TYPES,
    ), status


@bp.route("/<int:type_id>/nueva", methods=["GET", "POST"])
def new(type_id):
    ct = get_type(type_id)
    entry = Entry(content_type=ct, status="borrador")
    if request.method == "POST":
        errors, data = save(ct, entry)
        if not errors:
            flash(f"Entrada «{entry.title}» creada.")
            return redirect(url_for("entries.edit", entry_id=entry.id))
        return render_form(ct, entry, data, errors, 422)
    defaults = {k: p["default"] for k, p in ct.fields if "default" in p}
    return render_form(ct, entry, defaults)


@bp.route("/entradas/<int:entry_id>", methods=["GET", "POST"])
def edit(entry_id):
    entry = get_entry(entry_id)
    ct = entry.content_type
    if request.method == "POST":
        errors, data = save(ct, entry)
        if not errors:
            flash("Cambios guardados.")
            return redirect(url_for("entries.edit", entry_id=entry.id))
        return render_form(ct, entry, data, errors, 422)
    return render_form(ct, entry, entry.data)


# --- Versiones (RF-12) -------------------------------------------------------------------


def versions_of(entry):
    q = select(EntryVersion).where(EntryVersion.entry_id == entry.id)
    return db.session.scalars(q.order_by(EntryVersion.id.desc())).all()


def diff(ct, old, new):
    """Campos que cambian entre dos versiones: [(etiqueta, antes, después)]."""
    labels = dict((k, p["title"]) for k, p in ct.fields)
    keys = list(labels) + [k for k in {**old.data, **new.data} if k not in labels]
    rows = [
        (labels.get(k, k), old.data.get(k), new.data.get(k))
        for k in keys
        if old.data.get(k) != new.data.get(k)
    ]
    if old.status != new.status:
        rows.append(("Estado", STATUSES[old.status], STATUSES[new.status]))
    return rows


@bp.route("/entradas/<int:entry_id>/versiones")
def versions(entry_id):
    entry = get_entry(entry_id)
    items = versions_of(entry)
    by_id = {v.id: v for v in items}
    a = by_id.get(request.args.get("a", type=int))
    b = by_id.get(request.args.get("b", type=int))
    if not (a and b) and len(items) > 1:
        a, b = items[1], items[0]  # por defecto: la anterior contra la actual
    if a and b and a.id > b.id:
        a, b = b, a
    rows = diff(entry.content_type, a, b) if a and b else []
    ctx = dict(entry=entry, items=items, a=a, b=b, rows=rows, STATUSES=STATUSES)
    if request.headers.get("HX-Request"):
        return render_template("content/_diff.html", **ctx)
    return render_template("content/versions.html", **ctx)


@bp.route("/entradas/<int:entry_id>/versiones/<int:version_id>/restaurar", methods=["POST"])
def restore(entry_id, version_id):
    entry = get_entry(entry_id)
    version = db.one_or_404(
        select(EntryVersion).where(EntryVersion.id == version_id, EntryVersion.entry_id == entry.id)
    )
    slug_key = entry.content_type.slug_field
    slug = version.data.get(slug_key) if slug_key else None
    if slug and db.session.scalar(
        select(Entry.id).where(
            Entry.content_type_id == entry.content_type_id, Entry.slug == slug, Entry.id != entry.id
        )
    ):
        flash("No se puede restaurar: otra entrada usa ahora el mismo slug.", "error")
        return go(url_for("entries.versions", entry_id=entry.id))

    entry.data, entry.slug, entry.status = dict(version.data), slug, version.status
    db.session.add(EntryVersion(entry_id=entry.id, data=entry.data, status=entry.status))
    sync_usages(entry)
    db.session.commit()
    flash("Versión restaurada. Se guardó como una versión nueva.")
    return go(url_for("entries.edit", entry_id=entry.id))


@bp.app_template_filter("entry_value")
def entry_value(value):
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "—" if value is None else value
