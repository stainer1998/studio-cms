"""Plantillas por código: árbol, editor, validación, vista previa y versiones (RF-16 a RF-19)."""

import re

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from app import CSP
from app.content.models import ContentType
from app.core.htmx import go
from app.extensions import db
from app.media.usages import sync_template_usages
from app.templating import engine
from app.templating.functions import FILTERS
from app.templating.models import MODES, PATH_PATTERN, Template, TemplateVersion

bp = Blueprint("templates", __name__, url_prefix="/plantillas")

# Monaco crea estilos en línea y no admite nonce: se permiten solo en la pantalla del editor.
EDITOR_CSP = CSP.replace(
    "default-src 'self';", "default-src 'self'; style-src 'self' 'unsafe-inline';"
)
# La vista previa es HTML del sitio: sin scripts y solo dentro del iframe del Studio.
PREVIEW_CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
FUNCTIONS = ["entradas", "entrada", "url_entrada", "media_url"]


def get_template(template_id):
    return db.one_or_404(select(Template).where(Template.id == template_id))


def all_templates():
    return db.session.scalars(select(Template).order_by(Template.path)).all()


def path_error(path, template=None):
    if not re.match(PATH_PATTERN, path):
        return (
            "Usa minúsculas, números y guiones, con carpetas separadas por «/» "
            "y terminada en .html."
        )
    taken = select(Template.id).where(Template.path == path)
    if template is not None:
        taken = taken.where(Template.id != template.id)
    if db.session.scalar(taken):
        return "Ya existe una plantilla con esa ruta."
    return None


def media_url_for(media_id, variant):
    if variant == "original":
        return url_for("media.file", media_id=media_id)
    return url_for("media.file", media_id=media_id, variant=variant)


def render_editor(template, source=None, errors=(), status=200):
    g.csp = EDITOR_CSP
    keys = db.session.scalars(select(ContentType.key).order_by(ContentType.key)).all()
    return render_template(
        "templating/editor.html",
        template=template,
        source=template.source if source is None else source,
        errors=errors,
        templates=all_templates(),
        MODES=MODES,
        cms={"functions": FUNCTIONS, "filters": list(FILTERS), "models": keys},
    ), status


@bp.route("/")
def index():
    first = db.session.scalar(select(Template).order_by(Template.path).limit(1))
    if first:
        return redirect(url_for("templates.edit", template_id=first.id))
    return render_template("templating/empty.html")


@bp.route("/nueva", methods=["GET", "POST"])
def new():
    path = request.form.get("path", request.args.get("ruta", "")).strip()
    error = None
    if request.method == "POST":
        error = path_error(path)
        if not error:
            template = Template(path=path, source="")
            db.session.add(template)
            db.session.flush()
            db.session.add(TemplateVersion(template_id=template.id, source=""))
            db.session.commit()
            flash(f"Plantilla «{path}» creada.")
            return go(url_for("templates.edit", template_id=template.id))
    return render_template(
        "templating/new.html", path=path, error=error, templates=all_templates()
    ), (422 if error else 200)


@bp.route("/<int:template_id>", methods=["GET", "POST"])
def edit(template_id):
    template = get_template(template_id)
    if request.method == "GET":
        return render_editor(template)
    if template.mode == "visual":
        flash("En modo visual el código es de solo lectura.", "error")
        return render_editor(template, status=409)
    source = request.form.get("source", "").replace("\r\n", "\n")
    errors = engine.check(source, template.path)
    if errors:
        return render_editor(template, source, errors, 422)
    if source != template.source:
        template.source = source
        db.session.add(TemplateVersion(template_id=template.id, source=source))
        sync_template_usages(template)
        db.session.commit()
        flash("Plantilla guardada como versión nueva.")
    return redirect(url_for("templates.edit", template_id=template.id))


@bp.route("/validar", methods=["POST"])
def validate():
    data = request.get_json(silent=True) or {}
    errors = engine.check(data.get("source", ""), data.get("path"))
    return jsonify(errors=[e.as_dict() for e in errors])


@bp.route("/<int:template_id>/vista-previa", methods=["POST"])
def preview(template_id):
    template = get_template(template_id)
    source = request.form.get("source", template.source)
    sample = request.form.get("datos") == "ejemplo"
    try:
        html = engine.render(source, sample=sample, media_url_for=media_url_for)
    except engine.RenderError as e:
        html = render_template("templating/preview_error.html", error=e)
    g.csp = PREVIEW_CSP
    return html


@bp.route("/<int:template_id>/renombrar", methods=["POST"])
def rename(template_id):
    template = get_template(template_id)
    path = request.form.get("path", "").strip()
    error = path_error(path, template)
    if error:
        flash(error, "error")
    elif path != template.path:
        users = engine.references(template.path)
        old, template.path = template.path, path
        db.session.commit()
        flash(f"Plantilla renombrada a «{path}».")
        if users:
            flash(f"Actualiza las referencias a «{old}» en: {', '.join(users)}.", "warning")
    return go(url_for("templates.edit", template_id=template.id))


@bp.route("/<int:template_id>/eliminar", methods=["GET", "POST"])
def delete(template_id):
    template = get_template(template_id)
    users = engine.references(template.path)
    if request.method == "GET":
        return render_template(
            "templating/delete.html", template=template, users=users, templates=all_templates()
        )
    db.session.delete(template)
    db.session.commit()
    flash(f"Plantilla «{template.path}» eliminada.")
    return go(url_for("templates.index"))


@bp.route("/<int:template_id>/convertir", methods=["POST"])
def to_code(template_id):
    """La conversión de visual a código es manual y explícita (RF-19)."""
    template = get_template(template_id)
    if template.mode == "visual":
        template.mode = "code"
        db.session.commit()
        flash("La plantilla ahora se edita por código. El editor visual ya no la modificará.")
    return go(url_for("templates.edit", template_id=template.id))


# --- Versiones (RF-18) -------------------------------------------------------------------


@bp.route("/<int:template_id>/versiones")
def versions(template_id):
    template = get_template(template_id)
    q = select(TemplateVersion).where(TemplateVersion.template_id == template.id)
    items = db.session.scalars(q.order_by(TemplateVersion.id.desc())).all()
    shown = next((v for v in items if v.id == request.args.get("v", type=int)), None)
    shown = shown or (items[0] if items else None)
    return render_template(
        "templating/versions.html",
        template=template,
        items=items,
        shown=shown,
        templates=all_templates(),
    )


@bp.route("/<int:template_id>/versiones/<int:version_id>/restaurar", methods=["POST"])
def restore(template_id, version_id):
    template = get_template(template_id)
    version = db.one_or_404(
        select(TemplateVersion).where(
            TemplateVersion.id == version_id, TemplateVersion.template_id == template.id
        )
    )
    if template.mode == "visual":
        flash("En modo visual el código es de solo lectura.", "error")
    elif errors := engine.check(version.source, template.path):
        flash(f"No se puede restaurar: {errors[0].message}", "error")
    else:
        template.source = version.source
        db.session.add(TemplateVersion(template_id=template.id, source=version.source))
        sync_template_usages(template)
        db.session.commit()
        flash("Versión restaurada. Se guardó como una versión nueva.")
        return go(url_for("templates.edit", template_id=template.id))
    return go(url_for("templates.versions", template_id=template.id))
